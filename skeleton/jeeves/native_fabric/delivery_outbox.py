"""Replay-fenced delivery outbox for committed native Jeeves work.

No external sends are performed by this module. A delivery intent contains
only hashes, channel IDs and authority bindings, never private answers.
A consumer may claim an intent once and acknowledge it with an HMAC from
an explicitly configured independent receiver key. An unknown send stays
claimed across process loss and is NEVER automatically resent.

A valid acknowledgement proves knowledge of the receiver key, NOT that a
human saw or accepted the content. Real UI/transport delivery, key custody,
privacy retention and device qualification require separate evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import secrets
import time
from typing import Any, Callable

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from .contracts import ContractHold, digest, exact_integer, fingerprint, identifier
from .durable_queue import DurableNativeQueue, DurableQueueHold


class NativeDeliveryHold(ContractHold):
    """A delivery intent, receiver approval or committed source is uncertain."""


_DELIVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_delivery_intents (
  delivery_id TEXT NOT NULL,
  tenant TEXT NOT NULL,
  subject TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,
  tokenizer_sha256 TEXT NOT NULL,
  scope_sha256 TEXT NOT NULL,
  order_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  output_sha256 TEXT NOT NULL,
  work_receipt_sha256 TEXT NOT NULL,
  nonce TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('pending','claimed','delivered','cancelled')),
  revision INTEGER NOT NULL,
  claim_sha256 TEXT,
  receiver_ack_sha256 TEXT,
  created_ns INTEGER NOT NULL,
  spec_sha256 TEXT NOT NULL,
  PRIMARY KEY (tenant,subject,model_sha256,tokenizer_sha256,delivery_id),
  UNIQUE (tenant,subject,model_sha256,tokenizer_sha256,order_id,channel)
)
"""


def _message(spec_sha256:str,receiver_id:str)->bytes:
    digest(spec_sha256)
    identifier(receiver_id,"receiver")
    return ("jeeves.native_delivery_ack.v1:"+receiver_id+":"+spec_sha256).encode("ascii")


def receiver_ack(
    *,spec_sha256:str,receiver_id:str,receiver_key:bytes,
)->str:
    """Receiver-side HMAC of a separately verified delivery event.

    This signer is only for a trusted local receiver. It does not make a
    fabricated model response or a source-only simulation evidence of
    an actual UI display, transport or user receipt.
    """
    if type(receiver_key) is not bytes or not 32<=len(receiver_key)<=4096:
        raise NativeDeliveryHold("independent bounded receiver key required")
    return hmac.new(receiver_key,_message(spec_sha256,receiver_id),
                    "sha256").hexdigest()


@dataclass(frozen=True,slots=True)
class DeliveryIntent:
    delivery_id:str
    scope_sha256:str
    order_id:str
    channel:str
    output_sha256:str
    work_receipt_sha256:str
    nonce:str
    created_ns:int

    def __post_init__(self):
        for x in (self.delivery_id,self.order_id,self.channel):
            identifier(x)
        for x in (self.scope_sha256,self.output_sha256,
                  self.work_receipt_sha256):
            digest(x)
        if type(self.nonce) is not str or len(self.nonce)!=32 or any(
            c not in "0123456789abcdef" for c in self.nonce
        ):
            raise NativeDeliveryHold("fresh private delivery nonce required")
        exact_integer(self.created_ns,maximum=10**30)

    @property
    def fingerprint(self)->str:
        return fingerprint({
            "schema":"jeeves.native_delivery_intent.v1",
            "delivery_id":self.delivery_id,"scope":self.scope_sha256,
            "order":self.order_id,"channel":self.channel,
            "output":self.output_sha256,
            "work_receipt":self.work_receipt_sha256,
            "nonce":self.nonce,"created_ns":self.created_ns,
        })


@dataclass(frozen=True,slots=True)
class DeliveryClaim:
    intent:DeliveryIntent
    token:str
    revision:int

    def __post_init__(self):
        if not isinstance(self.intent,DeliveryIntent):
            raise NativeDeliveryHold("typed delivery intent required")
        if type(self.token) is not str or len(self.token)!=64 or any(
            c not in "0123456789abcdef" for c in self.token
        ):
            raise NativeDeliveryHold("fresh opaque claim token required")
        exact_integer(self.revision,minimum=1)


class NativeDeliveryOutbox:
    """Payload-free at-most-once send intent with receiver-HMAC acknowledgment."""

    def __init__(
        self,queue:DurableNativeQueue,*,receiver_id:str,
        receiver_key:bytes,maximum_intents:int=10000,
        clock_ns:Callable[[],int]=time.time_ns,
    ):
        if not isinstance(queue,DurableNativeQueue):
            raise NativeDeliveryHold("native durable queue authority required")
        identifier(receiver_id,"receiver")
        if type(receiver_key) is not bytes or not 32<=len(receiver_key)<=4096:
            raise NativeDeliveryHold("receiver key must be independently held")
        exact_integer(maximum_intents,minimum=1,maximum=100000)
        if not callable(clock_ns):
            raise NativeDeliveryHold("bounded receiver clock required")
        self.queue=queue
        self.worker=queue.worker
        self.db=queue.db
        self.identity=ActiveModel.from_supervisor(self.worker)
        self.scope_sha256=queue.scope_sha256
        self.receiver_id=receiver_id
        self._receiver_key=receiver_key
        self.maximum_intents=maximum_intents
        self.clock_ns=clock_ns
        self.db.inspect()
        with self.db.transaction() as conn:
            conn.execute(_DELIVERY_SCHEMA)

    def _scope(self):
        x=self.identity
        return x.tenant,x.subject,x.model_sha256,x.tokenizer_sha256

    def _live(self):
        if ActiveModel.from_supervisor(self.worker)!=self.identity:
            raise NativeDeliveryHold("receiver principal/model epoch changed")
        self.queue._live()

    def _select(self,conn,delivery_id):
        identifier(delivery_id,"delivery")
        row=conn.execute(
          "SELECT scope_sha256,order_id,channel,output_sha256,"
          "work_receipt_sha256,nonce,created_ns,state,revision,"
          "claim_sha256,receiver_ack_sha256,spec_sha256 "
          "FROM jeeves_native_delivery_intents WHERE "
          "tenant=? AND subject=? AND model_sha256=? "
          "AND tokenizer_sha256=? AND delivery_id=?",
          (*self._scope(),delivery_id),
        ).fetchone()
        if row is None:
            raise NativeDeliveryHold("delivery intent not found for this owner")
        intent=DeliveryIntent(delivery_id,*row[:7])
        if intent.scope_sha256!=self.scope_sha256 or intent.fingerprint!=row[11]:
            raise NativeDeliveryHold("delivery intent principal or spec changed")
        return intent,row

    def _public(self,intent,row):
        return {
          "schema":"jeeves.native_delivery_status.v1",
          "delivery_id":intent.delivery_id,
          "scope_sha256":intent.scope_sha256,
          "order_id":intent.order_id,"channel":intent.channel,
          "output_sha256":intent.output_sha256,
          "work_receipt_sha256":intent.work_receipt_sha256,
          "spec_sha256":intent.fingerprint,
          "state":row[7],"revision":row[8],
          "receiver_ack_sha256":row[10],
          "requires_receiver_verification":True,
          "payload_bytes_stored":False,
          "external_transport_completed_here":False,
          "human_delivery_proven":False,
          "release_certified":False,
        }

    def prepare(self,*,delivery_id:str,order_id:str,channel:str):
        """Only a committed, receipt-bound work item may reach outbox."""
        self._live()
        identifier(delivery_id,"delivery")
        identifier(channel,"channel")
        order=self.queue.inspect(order_id)
        if (order["state"]!="committed" or
            order["native_output_sha256"] is None or
            order["receipt_sha256"] is None):
            raise NativeDeliveryHold("uncommitted work cannot be prepared for delivery")
        intent=DeliveryIntent(
            delivery_id,self.scope_sha256,order_id,channel,
            order["native_output_sha256"],order["receipt_sha256"],
            secrets.token_hex(16),
            exact_integer(self.clock_ns(),maximum=10**30),
        )
        with self.db.transaction() as conn:
            count=conn.execute(
              "SELECT COUNT(*) FROM jeeves_native_delivery_intents "
              "WHERE tenant=? AND subject=? AND model_sha256=? "
              "AND tokenizer_sha256=?",
              self._scope(),
            ).fetchone()[0]
            if count>=self.maximum_intents:
                raise NativeDeliveryHold("delivery intent inventory full")
            conn.execute(
              "INSERT INTO jeeves_native_delivery_intents "
              "(delivery_id,tenant,subject,model_sha256,tokenizer_sha256,"
              "scope_sha256,order_id,channel,output_sha256,"
              "work_receipt_sha256,nonce,state,revision,created_ns,spec_sha256) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?)",
              (intent.delivery_id,*self._scope(),intent.scope_sha256,
               intent.order_id,intent.channel,intent.output_sha256,
               intent.work_receipt_sha256,intent.nonce,
               intent.created_ns,intent.fingerprint),
            )
            return self._public(*self._select(conn,delivery_id))

    def inspect(self,delivery_id):
        self._live()
        with self.db.snapshot() as conn:
            return self._public(*self._select(conn,delivery_id))

    def claim(self,delivery_id)->DeliveryClaim:
        self._live()
        token=secrets.token_hex(32)
        token_hash=sha256(token.encode("ascii")).hexdigest()
        with self.db.transaction() as conn:
            intent,row=self._select(conn,delivery_id)
            if row[7]!="pending":
                raise NativeDeliveryHold("delivery already claimed or terminal")
            # Recheck source work has not changed since preparation.
            # Reuse the held SQLite write transaction. Opening the queue's
            # separate snapshot here would nest BEGIN on the same authority.
            work_order,work_row=self.queue._select(conn,intent.order_id)
            if (work_row[14]!="committed" or
                work_row[17]!=intent.output_sha256 or
                work_row[18]!=intent.work_receipt_sha256):
                raise NativeDeliveryHold("native source receipt changed before send")
            conn.execute(
              "UPDATE jeeves_native_delivery_intents SET state='claimed',"
              "revision=revision+1,claim_sha256=? "
              "WHERE delivery_id=? AND tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? "
              "AND revision=? AND state='pending'",
              (token_hash,delivery_id,*self._scope(),row[8]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise NativeDeliveryHold("delivery claim lost CAS")
            return DeliveryClaim(intent,token,row[8]+1)

    def _verify_ack(self,intent,received):
        if type(received) is not str or len(received)!=64 or any(
            c not in "0123456789abcdef" for c in received
        ):
            raise NativeDeliveryHold("receiver HMAC must be lowercase sha256")
        expected=receiver_ack(
            spec_sha256=intent.fingerprint,
            receiver_id=self.receiver_id,
            receiver_key=self._receiver_key,
        )
        if not hmac.compare_digest(received,expected):
            raise NativeDeliveryHold("receiver acknowledgment signature mismatch")
        return sha256(received.encode("ascii")).hexdigest()

    def acknowledge(self,claim:DeliveryClaim,*,receiver_hmac:str):
        """No network action, just verified acknowledgement of an existing claim."""
        self._live()
        if not isinstance(claim,DeliveryClaim):
            raise NativeDeliveryHold("typed delivery claim required")
        with self.db.transaction() as conn:
            intent,row=self._select(conn,claim.intent.delivery_id)
            if intent!=claim.intent or row[7]!="claimed" or row[8]!=claim.revision:
                raise NativeDeliveryHold("stale or foreign delivery claim")
            if row[9]!=sha256(claim.token.encode("ascii")).hexdigest():
                raise NativeDeliveryHold("delivery claim secret differs")
            signature_hash=self._verify_ack(intent,receiver_hmac)
            conn.execute(
              "UPDATE jeeves_native_delivery_intents SET state='delivered',"
              "revision=revision+1,receiver_ack_sha256=? "
              "WHERE delivery_id=? AND tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? AND revision=?",
              (signature_hash,intent.delivery_id,*self._scope(),row[8]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise NativeDeliveryHold("delivery acknowledgment lost CAS")
        return self.inspect(intent.delivery_id)

    def reconcile_orphaned(self,delivery_id,*,receiver_hmac,
                           operator_approved:bool):
        """Reconcile lost process claim without re-sending the payload."""
        if operator_approved is not True:
            raise NativeDeliveryHold("explicit operator orphan reconciliation required")
        self._live()
        with self.db.transaction() as conn:
            intent,row=self._select(conn,delivery_id)
            if row[7]!="claimed":
                raise NativeDeliveryHold("no orphaned delivery to reconcile")
            signed_hash=self._verify_ack(intent,receiver_hmac)
            conn.execute(
              "UPDATE jeeves_native_delivery_intents SET state='delivered',"
              "revision=revision+1,receiver_ack_sha256=? "
              "WHERE delivery_id=? AND tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? AND revision=?",
              (signed_hash,delivery_id,*self._scope(),row[8]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise NativeDeliveryHold("orphan reconciliation lost CAS")
        return self.inspect(delivery_id)

    def cancel_pending(self,delivery_id):
        self._live()
        with self.db.transaction() as conn:
            intent,row=self._select(conn,delivery_id)
            if row[7]!="pending":
                raise NativeDeliveryHold("claimed transport cannot be presumed unsent")
            conn.execute(
              "UPDATE jeeves_native_delivery_intents "
              "SET state='cancelled',revision=revision+1 "
              "WHERE delivery_id=? AND tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? AND revision=?",
              (delivery_id,*self._scope(),row[8]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise NativeDeliveryHold("delivery cancellation lost CAS")
        return self.inspect(delivery_id)

    def snapshot(self):
        self._live()
        with self.db.snapshot() as conn:
            counts=dict(conn.execute(
              "SELECT state,COUNT(*) FROM jeeves_native_delivery_intents "
              "WHERE tenant=? AND subject=? AND model_sha256=? "
              "AND tokenizer_sha256=? GROUP BY state",
              self._scope(),
            ).fetchall())
        return {
          "schema":"jeeves.native_delivery_outbox.v1",
          "counts":counts,
          "automatic_resend":False,
          "receiver_ack_key_in_process":True,
          "real_network_or_UI_delivery_qualified":False,
          "release_certified":False,
        }


__all__=["NativeDeliveryHold","DeliveryIntent","DeliveryClaim",
         "receiver_ack","NativeDeliveryOutbox"]
