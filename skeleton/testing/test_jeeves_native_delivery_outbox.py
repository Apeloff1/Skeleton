"""Payload-free delivery outbox using real protected SQLite and synthetic GGUF.

Native model generation is synthetic; all native turn receipts, replay,
HMAC verification, at-most-once claim and cold-process custody use real
production code. Receiver HMAC does NOT attest human-visible UX or network.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.contracts import Scope
from skeleton.jeeves.native_fabric.durable_queue import (
    DurableNativeQueue,WorkOrder,
)
from skeleton.jeeves.native_fabric.delivery_outbox import (
    NativeDeliveryHold,NativeDeliveryOutbox,receiver_ack,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "private descriptor-anchored SQLite requires Linux")
class TestNativeDeliveryOutbox(unittest.TestCase):
    SESSION="delivery_session"
    REQUEST="delivery_request"
    PROMPT="Private user answer that must not enter outbox metadata"
    KEY=bytes.fromhex("7d"*32)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)
        self._seed_order()

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _open(self,*,subject="operator"):
        self.db=SpineDatabase(self.tmp.name)
        self.gate=SessionGate(self.tmp.name)
        self.backend=SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        )
        self.worker=SupervisedAI(self.spine)
        self.scope=Scope("local","operator",MODEL,TOKENIZER)
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=self.scope.binding,
            clock_ns=lambda:1000000,
        )
        self.outbox=NativeDeliveryOutbox(
            self.queue,receiver_id="laptop_screen",
            receiver_key=self.KEY,clock_ns=lambda:1000000,
        )

    def _cold(self,*,subject="operator"):
        self._close()
        self._open(subject=subject)

    def _seed_order(self):
        self.order=WorkOrder(
            "delivery_order",self.scope.binding,"local","operator",MODEL,TOKENIZER,
            self.SESSION,self.REQUEST,sha256(self.PROMPT.encode()).hexdigest(),
            0,0.8,"operator",5,1000000,10000000,
        )
        self.spine.create(self.SESSION)
        self.queue.submit(self.order)

    def _commit(self):
        claim=self.queue.claim(self.order.order_id)
        self.queue.execute_claimed(
            claim,prompt=self.PROMPT,operator_approved=True,
        )
        self.assertEqual(self.backend.calls,1)

    def _prepare(self,*,delivery_id="delivery_one",channel="local_console"):
        return self.outbox.prepare(
            delivery_id=delivery_id,
            order_id=self.order.order_id,
            channel=channel,
        )

    def _ack(self,delivery_id="delivery_one"):
        published=self.outbox.inspect(delivery_id)
        return receiver_ack(
            spec_sha256=published["spec_sha256"],
            receiver_id="laptop_screen",
            receiver_key=self.KEY,
        )

    def test_uncommitted_work_cannot_be_sent(self):
        with self.assertRaises(NativeDeliveryHold):
            self._prepare()
        self.assertEqual(self.outbox.snapshot()["counts"],{})

    def test_prepare_stores_no_response_text(self):
        self._commit()
        record=self._prepare()
        self.assertEqual(record["state"],"pending")
        self.assertFalse(record["payload_bytes_stored"])
        self.assertNotIn(self.PROMPT,str(record))
        self.assertNotIn(self.backend.answer,str(record))
        with self.db.snapshot() as conn:
            sql=conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name='jeeves_native_delivery_intents'",
            ).fetchone()[0]
        self.assertNotIn("response_text",sql)

    def test_claim_prevents_automatic_second_dispatch(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        self.assertEqual(self.outbox.inspect("delivery_one")["state"],"claimed")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.claim("delivery_one")
        self.assertEqual(self.backend.calls,1)

    def test_valid_receiver_hmac_marks_delivered(self):
        self._commit()
        self._prepare()
        claimed=self.outbox.claim("delivery_one")
        published=self.outbox.acknowledge(
            claimed,receiver_hmac=self._ack(),
        )
        self.assertEqual(published["state"],"delivered")
        self.assertEqual(self.outbox.snapshot()["counts"]["delivered"],1)

    def test_wrong_receiver_hmac_never_delivers(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.acknowledge(
                claim,receiver_hmac="f"*64,
            )
        self.assertEqual(self.outbox.inspect("delivery_one")["state"],"claimed")

    def test_invalid_receiver_key_is_rejected(self):
        with self.assertRaises(NativeDeliveryHold):
            NativeDeliveryOutbox(
                self.queue,receiver_id="laptop",
                receiver_key=b"short",
            )

    def test_ack_signature_bound_to_receiver_identity(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        bad=receiver_ack(
            spec_sha256=claim.intent.fingerprint,
            receiver_id="foreign_receiver",
            receiver_key=self.KEY,
        )
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.acknowledge(claim,receiver_hmac=bad)

    def test_ack_signature_bound_to_immutable_delivery_nonce(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        fake=receiver_ack(
            spec_sha256="f"*64,
            receiver_id="laptop_screen",receiver_key=self.KEY,
        )
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.acknowledge(claim,receiver_hmac=fake)

    def test_duplicate_delivery_id_or_channel_denied(self):
        self._commit()
        self._prepare()
        with self.assertRaises(Exception):
            self._prepare()
        with self.assertRaises(Exception):
            self._prepare(delivery_id="different_id",channel="local_console")

    def test_same_order_can_have_separate_explicit_receiver_channels(self):
        self._commit()
        self._prepare(channel="local_console")
        self._prepare(delivery_id="second_channel",channel="local_file")
        self.assertEqual(self.outbox.snapshot()["counts"]["pending"],2)

    def test_pending_delivery_can_be_cancelled_without_unknown_effect(self):
        self._commit()
        self._prepare()
        cancelled=self.outbox.cancel_pending("delivery_one")
        self.assertEqual(cancelled["state"],"cancelled")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.claim("delivery_one")

    def test_claimed_delivery_cannot_be_cancelled_as_unsent(self):
        self._commit()
        self._prepare()
        self.outbox.claim("delivery_one")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.cancel_pending("delivery_one")

    def test_duplicate_ack_replay_denied(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        signature=self._ack()
        self.outbox.acknowledge(claim,receiver_hmac=signature)
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.acknowledge(claim,receiver_hmac=signature)

    def test_stale_or_forged_claim_cannot_ack(self):
        self._commit()
        self._prepare()
        claim=self.outbox.claim("delivery_one")
        forged=replace(claim,token="f"*64)
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.acknowledge(
                forged,receiver_hmac=self._ack(),
            )

    def test_cold_reopen_preserves_claim_without_new_delivery(self):
        self._commit()
        self._prepare()
        self.outbox.claim("delivery_one")
        self._cold()
        self.assertEqual(self.outbox.inspect("delivery_one")["state"],"claimed")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.claim("delivery_one")
        self.assertEqual(self.backend.calls,0)

    def test_cold_orphan_requires_valid_receiver_hmac(self):
        self._commit()
        self._prepare()
        self.outbox.claim("delivery_one")
        self._cold()
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.reconcile_orphaned(
                "delivery_one",receiver_hmac="f"*64,
                operator_approved=True,
            )
        self.assertEqual(self.outbox.inspect("delivery_one")["state"],"claimed")

    def test_cold_orphan_reconciles_without_resending(self):
        self._commit()
        self._prepare()
        signature=self._ack()
        self.outbox.claim("delivery_one")
        self._cold()
        report=self.outbox.reconcile_orphaned(
            "delivery_one",receiver_hmac=signature,
            operator_approved=True,
        )
        self.assertEqual(report["state"],"delivered")
        self.assertFalse(report["external_transport_completed_here"])
        self.assertEqual(self.backend.calls,0)

    def test_orphan_reconciliation_requires_operator_approval(self):
        self._commit()
        self._prepare()
        self.outbox.claim("delivery_one")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.reconcile_orphaned(
                "delivery_one",receiver_hmac=self._ack(),
                operator_approved=False,
            )

    def test_foreign_subject_cannot_view_delivery(self):
        self._commit()
        self._prepare()
        self._cold(subject="foreign")
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.inspect("delivery_one")
        self.assertEqual(self.outbox.snapshot()["counts"],{})

    def test_persisted_payload_digest_tamper_is_detected(self):
        self._commit()
        self._prepare()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_delivery_intents SET output_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.inspect("delivery_one")

    def test_persisted_spec_hash_tamper_is_detected(self):
        self._commit()
        self._prepare()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_delivery_intents SET spec_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.claim("delivery_one")

    def test_delivery_inventory_full_denies_second_new_intent(self):
        self._commit()
        self.outbox=NativeDeliveryOutbox(
            self.queue,receiver_id="laptop_screen",receiver_key=self.KEY,
            maximum_intents=1,clock_ns=lambda:1000000,
        )
        self._prepare()
        with self.assertRaises(NativeDeliveryHold):
            self._prepare(
                delivery_id="other_delivery",channel="other",
            )

    def test_source_work_receipt_corruption_blocks_claim(self):
        self._commit()
        self._prepare()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_work_orders SET receipt_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeDeliveryHold):
            self.outbox.claim("delivery_one")

    def test_snapshot_never_claims_external_send_was_performed(self):
        self._commit()
        self._prepare()
        report=self.outbox.snapshot()
        self.assertFalse(report["real_network_or_UI_delivery_qualified"])
        self.assertFalse(report["automatic_resend"])
        self.assertFalse(report["release_certified"])


if __name__=="__main__":
    unittest.main()
