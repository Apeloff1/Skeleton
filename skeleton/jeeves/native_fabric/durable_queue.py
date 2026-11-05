"""Restart-fenced native inference work orders in the existing SQLite authority.

No second database, no provider fallback and no model-generated permissions.
Queue submission holds only a prompt SHA256 (not private prompt bytes), session,
request identity and a principal/model binding. A claim is a one-way durable
transition: process loss leaves it CLAIMED, not eligible for a fresh worker.
Reconciliation requires the exact original prompt and the authoritative
execution-spine committed replay, never an operator's success assertion.

This is an opt-in scheduling surface, not a replacement for the existing
SessionGate, native request reservation, signed model installation or CI gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import secrets
import threading
import time
from typing import Any, Callable

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from .contracts import ContractHold, digest, exact_integer, fingerprint, identifier, text


class DurableQueueHold(ContractHold):
    """Queue claim, principal, native effect or custody could not be proven."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_work_orders (
  order_id TEXT PRIMARY KEY,
  scope_sha256 TEXT NOT NULL,
  tenant TEXT NOT NULL,
  subject TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,
  tokenizer_sha256 TEXT NOT NULL,
  session_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  prompt_sha256 TEXT NOT NULL,
  seed INTEGER NOT NULL,
  temperature_repr TEXT NOT NULL,
  cohort TEXT NOT NULL,
  priority INTEGER NOT NULL,
  admitted_ns INTEGER NOT NULL,
  expires_ns INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN
    ('queued','claimed','committed','held','cancelled')),
  revision INTEGER NOT NULL,
  claim_sha256 TEXT,
  native_output_sha256 TEXT,
  receipt_sha256 TEXT,
  reason TEXT,
  spec_sha256 TEXT NOT NULL,
  UNIQUE(session_id, request_id, tenant, subject, model_sha256, tokenizer_sha256)
)
"""

@dataclass(frozen=True, slots=True)
class WorkOrder:
    order_id: str
    scope_sha256: str
    tenant: str
    subject: str
    model_sha256: str
    tokenizer_sha256: str
    session_id: str
    request_id: str
    prompt_sha256: str
    seed: int
    temperature: float
    cohort: str
    priority: int
    admitted_ns: int
    expires_ns: int

    def __post_init__(self):
        for name in ("order_id","tenant","subject","session_id","request_id","cohort"):
            identifier(getattr(self,name),name)
        for name in ("scope_sha256","model_sha256","tokenizer_sha256","prompt_sha256"):
            digest(getattr(self,name))
        exact_integer(self.seed,maximum=2**32-1)
        if type(self.temperature) not in (int,float) or not 0.000000001 <= self.temperature <= 2:
            raise DurableQueueHold("native temperature must be finite and in range")
        exact_integer(self.priority,maximum=1000)
        exact_integer(self.admitted_ns,maximum=10**30)
        exact_integer(self.expires_ns,maximum=10**30)
        if self.expires_ns <= self.admitted_ns:
            raise DurableQueueHold("work order expiration is invalid")

    @property
    def spec_sha256(self)->str:
        return fingerprint({
            "schema":"jeeves.native_work_order.v1",
            "order_id":self.order_id,"scope":self.scope_sha256,
            "tenant":self.tenant,"subject":self.subject,
            "model":self.model_sha256,"tokenizer":self.tokenizer_sha256,
            "session_id":self.session_id,"request_id":self.request_id,
            "prompt_sha256":self.prompt_sha256,
            "seed":self.seed,"temperature":repr(float(self.temperature)),
            "cohort":self.cohort,"priority":self.priority,
            "admitted_ns":self.admitted_ns,"expires_ns":self.expires_ns,
        })


@dataclass(frozen=True, slots=True)
class WorkClaim:
    order: WorkOrder
    token: str
    revision: int

    def __post_init__(self):
        if not isinstance(self.order,WorkOrder):
            raise DurableQueueHold("typed work order required")
        if type(self.token) is not str or len(self.token)!=64 or any(x not in "0123456789abcdef" for x in self.token):
            raise DurableQueueHold("unforgeable random claim token required")
        exact_integer(self.revision,minimum=1)


class DurableNativeQueue:
    """Canonical database-backed queue with no crash-driven reissue.

    All mutating operations use the authoritative SpineDatabase transaction,
    which holds BEGIN IMMEDIATE. The raw claim token is never persisted; only
    its SHA256 is retained and it is not exposed by inspections.
    """

    def __init__(self,worker:Any,*,scope_sha256:str,
                 maximum_orders:int=10000,
                 clock_ns:Callable[[],int]=time.time_ns):
        if worker is None or not hasattr(worker,"spine"):
            raise DurableQueueHold("production native worker required")
        if not isinstance(worker.spine.db,SpineDatabase):
            raise DurableQueueHold("descriptor-anchored SQLite required")
        digest(scope_sha256)
        exact_integer(maximum_orders,minimum=1,maximum=100000)
        if not callable(clock_ns):
            raise DurableQueueHold("host clock required")
        self.worker=worker
        self.db=worker.spine.db
        self.active=ActiveModel.from_supervisor(worker)
        self.scope_sha256=scope_sha256
        self.maximum_orders=maximum_orders
        self.clock_ns=clock_ns
        self._lock=threading.RLock()
        self.db.inspect()
        with self.db.transaction() as conn:
            conn.execute(_SCHEMA)

    def _live(self):
        if ActiveModel.from_supervisor(self.worker)!=self.active:
            raise DurableQueueHold("native model principal changed")

    def _scope(self):
        i=self.active
        return i.tenant,i.subject,i.model_sha256,i.tokenizer_sha256

    def _now(self)->int:
        now=self.clock_ns()
        return exact_integer(now,maximum=10**30)

    def _select(self,conn,order_id):
        identifier(order_id,"order")
        row=conn.execute(
          "SELECT scope_sha256,tenant,subject,model_sha256,tokenizer_sha256,"
          "session_id,request_id,prompt_sha256,seed,temperature_repr,"
          "cohort,priority,admitted_ns,expires_ns,state,revision,"
          "claim_sha256,native_output_sha256,receipt_sha256,reason,spec_sha256 "
          "FROM jeeves_native_work_orders WHERE order_id=?",(order_id,),
        ).fetchone()
        if row is None:
            raise DurableQueueHold("native work order absent")
        if (row[0]!=self.scope_sha256 or tuple(row[1:5])!=self._scope()):
            raise DurableQueueHold("foreign work order principal/model")
        try:
            order=WorkOrder(
              order_id,self.scope_sha256,*row[1:5],*row[5:9],
              float(row[9]),row[10],row[11],row[12],row[13],
            )
        except (ValueError,TypeError) as exc:
            raise DurableQueueHold("malformed durable queue row") from exc
        if order.spec_sha256!=row[20]:
            raise DurableQueueHold("durable work order specification changed")
        return order,row

    def _public(self,order,row):
        return {
          "schema":"jeeves.native_work_order_status.v1",
          "order_id":order.order_id,"scope_sha256":order.scope_sha256,
          "session_id":order.session_id,"request_id":order.request_id,
          "prompt_sha256":order.prompt_sha256,
          "state":row[14],"revision":row[15],
          "native_output_sha256":row[17],
          "receipt_sha256":row[18],"hold_reason":row[19],
          "claim_secret_disclosed":False,
          "model_rights_independently_verified":False,
          "device_qualified":False,"release_certified":False,
        }

    def _insert_many(self,conn,orders):
        """Atomic work-intent insert inside caller's canonical SQLite transaction.

        Partial batch admission must never survive a crash: callers pass
        the protected SpineDatabase transaction, not an arbitrary connection.
        No native effect occurs. Existing occupied request IDs remain a hold.
        """
        if conn is not self.db._db:
            raise DurableQueueHold("canonical SQLite transaction required")
        self._live()
        if type(orders) not in (tuple,list) or not 1<=len(orders)<=10000:
            raise DurableQueueHold("bounded nonempty typed work inventory required")
        keys=set()
        for order in orders:
            if not isinstance(order,WorkOrder):
                raise DurableQueueHold("typed work order required")
            if (order.scope_sha256!=self.scope_sha256 or
                (order.tenant,order.subject,order.model_sha256,
                 order.tokenizer_sha256)!=self._scope()):
                raise DurableQueueHold("foreign work cannot enter queue")
            if order.expires_ns<=self._now():
                raise DurableQueueHold("already expired work order")
            key=(order.session_id,order.request_id)
            if key in keys:
                raise DurableQueueHold("duplicate native session/request in one admission")
            keys.add(key)
        count=conn.execute(
          "SELECT COUNT(*) FROM jeeves_native_work_orders WHERE "
          "tenant=? AND subject=? AND model_sha256=? AND tokenizer_sha256=?",
          self._scope(),
        ).fetchone()[0]
        if count+len(orders)>self.maximum_orders:
            raise DurableQueueHold("work-order inventory full")
        receipts=[]
        for order in orders:
            conn.execute(
              "INSERT INTO jeeves_native_work_orders "
              "(order_id,scope_sha256,tenant,subject,model_sha256,tokenizer_sha256,"
              "session_id,request_id,prompt_sha256,seed,temperature_repr,cohort,"
              "priority,admitted_ns,expires_ns,state,revision,spec_sha256)"
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'queued',0,?)",
              (order.order_id,order.scope_sha256,*self._scope(),
               order.session_id,order.request_id,order.prompt_sha256,
               order.seed,repr(float(order.temperature)),order.cohort,
               order.priority,order.admitted_ns,order.expires_ns,
               order.spec_sha256),
            )
            receipts.append(self._public(order,self._select(conn,order.order_id)[1]))
        return tuple(receipts)

    def submit_many(self,orders):
        """All-or-nothing new native work, no model activation."""
        with self.db.transaction() as conn:
            return self._insert_many(conn,orders)

    def submit(self,order:WorkOrder):
        return self.submit_many((order,))[0]

    def inspect(self,order_id:str)->dict[str,object]:
        self._live()
        with self.db.snapshot() as conn:
            order,row=self._select(conn,order_id)
            return self._public(order,row)

    def inventory(self,*,limit:int=256)->tuple[dict[str,object],...]:
        self._live()
        exact_integer(limit,minimum=1,maximum=10000)
        with self.db.snapshot() as conn:
            ids=[row[0] for row in conn.execute(
              "SELECT order_id FROM jeeves_native_work_orders WHERE "
              "scope_sha256=? AND tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? "
              "ORDER BY admitted_ns,order_id LIMIT ?",
              (self.scope_sha256,*self._scope(),limit),
            ).fetchall()]
            return tuple(self._public(*self._select(conn,x)) for x in ids)

    def claim(self,order_id:str)->WorkClaim:
        self._live()
        token=secrets.token_hex(32)
        token_sha=sha256(token.encode("ascii")).hexdigest()
        with self.db.transaction() as conn:
            order,row=self._select(conn,order_id)
            if row[14]!="queued":
                raise DurableQueueHold("already claimed or terminal work order")
            if self._now()>=order.expires_ns:
                conn.execute(
                  "UPDATE jeeves_native_work_orders SET state='cancelled',"
                  "revision=revision+1,reason='expired_before_inference' "
                  "WHERE order_id=? AND state='queued'",(order_id,),
                )
                raise DurableQueueHold("expired queued work cannot be inferred")
            conn.execute(
              "UPDATE jeeves_native_work_orders "
              "SET state='claimed',revision=revision+1,claim_sha256=? "
              "WHERE order_id=? AND state='queued' AND revision=?",
              (token_sha,order_id,row[15]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise DurableQueueHold("claim revision changed")
            return WorkClaim(order,token,row[15]+1)

    def next_ready(self,*,limit:int=16)->tuple[str,...]:
        """Return candidate identities, not a claim or native permission."""
        self._live()
        exact_integer(limit,minimum=1,maximum=10000)
        with self.db.snapshot() as conn:
            return tuple(row[0] for row in conn.execute(
              "SELECT order_id FROM jeeves_native_work_orders "
              "WHERE state='queued' AND scope_sha256=? "
              "AND tenant=? AND subject=? AND model_sha256=? "
              "AND tokenizer_sha256=? AND expires_ns>? "
              "ORDER BY priority DESC,admitted_ns,order_id LIMIT ?",
              (self.scope_sha256,*self._scope(),self._now(),limit),
            ).fetchall())

    def cancel_queued(self,order_id:str):
        self._live()
        with self.db.transaction() as conn:
            order,row=self._select(conn,order_id)
            if row[14]!="queued":
                raise DurableQueueHold("claimed native work may already have executed")
            conn.execute(
              "UPDATE jeeves_native_work_orders SET state='cancelled',"
              "reason='explicit_preclaim_cancel',revision=revision+1 "
              "WHERE order_id=? AND state='queued'",(order_id,),
            )
            return self._public(order,self._select(conn,order_id)[1])

    def quarantine(self,claim:WorkClaim,*,code:str="uncertain_effect"):
        identifier(code,"hold reason")
        self._live()
        with self.db.transaction() as conn:
            order,row=self._checked_claim(conn,claim)
            conn.execute(
              "UPDATE jeeves_native_work_orders SET state='held',reason=?,"
              "revision=revision+1 WHERE order_id=? AND revision=?",
              (code,order.order_id,row[15]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise DurableQueueHold("lost held-work revision")
            return self._public(order,self._select(conn,order.order_id)[1])

    def _checked_claim(self,conn,claim:WorkClaim,*,allow_held:bool=False):
        if not isinstance(claim,WorkClaim):
            raise DurableQueueHold("typed claim required")
        order,row=self._select(conn,claim.order.order_id)
        if (order!=claim.order or
            row[14] not in (("claimed","held") if allow_held else ("claimed",)) or
            row[16]!=sha256(claim.token.encode("ascii")).hexdigest()):
            raise DurableQueueHold("invalid stale or foreign claim")
        if (row[15] != claim.revision and
            not (allow_held and row[15] == claim.revision+1)):
            raise DurableQueueHold("claim revision no longer matches")
        return order,row

    def _verified_receipt(self,order:WorkOrder,prompt:str):
        text(prompt,maximum_bytes=self.worker.spine.limits.input_bytes)
        if sha256(prompt.encode("utf-8","strict")).hexdigest()!=order.prompt_sha256:
            raise DurableQueueHold("operator prompt differs from durably admitted bytes")
        self._live()
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
            Conflict, Busy,
        )
        try:
            saved=self.worker.spine.replay(
              order.session_id,order.request_id,prompt,
              seed=order.seed,temperature=order.temperature,
            )
        except (Conflict, Busy) as exc:
            # Missing, foreign, closed or still-pending native sessions
            # cannot prove a committed result. Never reset their claim.
            raise DurableQueueHold(
                "native session cannot prove committed orphan receipt"
            ) from exc
        if saved is None:
            raise DurableQueueHold("no authoritative native commit to reconcile")
        proven=verify_turn_receipt(
          saved,model_sha256=order.model_sha256,
          tokenizer_sha256=order.tokenizer_sha256,
        )
        if proven.get("replayed") is not True:
            raise DurableQueueHold("must prove read-only committed replay")
        return proven

    def reconcile(self,claim:WorkClaim,*,prompt:str,
                  operator_approved:bool=False):
        """Seal only a replay-verified GGUF output, including a held claim.

        This function never starts native generation. Reconciliation after
        uncertainty requires fresh explicit operator approval.
        """
        if type(operator_approved) is not bool:
            raise DurableQueueHold("strict operator approval boolean required")
        self._live()
        with self.db.snapshot() as conn:
            order,row=self._checked_claim(conn,claim,allow_held=operator_approved)
            if row[14]=="held" and not operator_approved:
                raise DurableQueueHold("held inference requires operator review")
        proven=self._verified_receipt(order,prompt)
        output=proven["output_sha256"]
        receipt_hash=fingerprint({
          "schema":"jeeves.native_work_order_receipt.v1",
          "order":order.spec_sha256,"output":output,
          "model":order.model_sha256,"tokenizer":order.tokenizer_sha256,
          "request":order.request_id,"session":order.session_id,
        })
        with self.db.transaction() as conn:
            old,prior=self._checked_claim(
                conn,claim,allow_held=operator_approved,
            )
            conn.execute(
              "UPDATE jeeves_native_work_orders SET state='committed',"
              "revision=revision+1,reason=NULL,native_output_sha256=?,"
              "receipt_sha256=? WHERE order_id=? AND revision=?",
              (output,receipt_hash,old.order_id,prior[15]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise DurableQueueHold("lost work-order reconciliation CAS")
        return self.inspect(order.order_id)

    def reconcile_orphaned(self,order_id:str,*,prompt:str,
                           operator_approved:bool):
        """Cold-process recovery without the vanished volatile claim token.

        A crash destroys a WorkClaim token, but this cannot justify a second
        model generation. A local operator may supply the exact original
        prompt and explicitly authorize a read-only lookup of the canonical
        native receipt. The source of truth is still ExecutionSpine.replay;
        an absent/pending receipt leaves the queue claimed or held.
        """
        if operator_approved is not True:
            raise DurableQueueHold("explicit independent orphan review required")
        self._live()
        with self.db.snapshot() as conn:
            order,row=self._select(conn,order_id)
            if row[14] not in ("claimed","held"):
                raise DurableQueueHold("not an orphaned native claim")
        verified=self._verified_receipt(order,prompt)
        output=verified["output_sha256"]
        receipt_hash=fingerprint({
          "schema":"jeeves.native_work_order_receipt.v1",
          "order":order.spec_sha256,"output":output,
          "model":order.model_sha256,"tokenizer":order.tokenizer_sha256,
          "request":order.request_id,"session":order.session_id,
        })
        with self.db.transaction() as conn:
            reread,current=self._select(conn,order_id)
            if reread!=order or current[14] not in ("claimed","held"):
                raise DurableQueueHold("orphan state changed during reconciliation")
            conn.execute(
              "UPDATE jeeves_native_work_orders SET state='committed',"
              "revision=revision+1,native_output_sha256=?,"
              "receipt_sha256=?,reason=NULL "
              "WHERE order_id=? AND revision=? AND state IN ('claimed','held')",
              (output,receipt_hash,order.order_id,current[15]),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise DurableQueueHold("orphan reconciliation lost revision CAS")
        return self.inspect(order_id)

    def execute_claimed(self,claim:WorkClaim,*,prompt:str,
                        operator_approved:bool):
        """Exactly one native call on an explicitly claimed work order.

        A caught inference exception leaves the claim in durable uncertainty,
        never a fresh queue item. Caller must inspect and reconcile committed
        receipts or hold it for separate investigation.
        """
        if operator_approved is not True:
            raise DurableQueueHold("explicit operator native inference approval required")
        self._live()
        with self.db.snapshot() as conn:
            order,_=self._checked_claim(conn,claim)
        text(prompt,maximum_bytes=self.worker.spine.limits.input_bytes)
        if sha256(prompt.encode("utf-8","strict")).hexdigest()!=order.prompt_sha256:
            raise DurableQueueHold("prompt binding changed before native generation")
        self.worker.turn(order.session_id,order.request_id,prompt,
                         seed=order.seed,temperature=order.temperature)
        return self.reconcile(claim,prompt=prompt)

    def no_autoretry_status(self):
        self._live()
        with self.db.snapshot() as conn:
            counts=dict(conn.execute(
              "SELECT state,COUNT(*) FROM jeeves_native_work_orders "
              "WHERE scope_sha256=? AND tenant=? AND subject=? AND "
              "model_sha256=? AND tokenizer_sha256=? GROUP BY state",
              (self.scope_sha256,*self._scope()),
            ).fetchall())
        return {
          "schema":"jeeves.native_durable_queue_status.v1",
          "counts":counts,"held_cannot_requeue":True,
          "claimed_cannot_requeue":True,
          "automatic_native_retry":False,
          "device_qualified":False,"release_certified":False,
        }


__all__=["DurableQueueHold","WorkOrder","WorkClaim","DurableNativeQueue"]
