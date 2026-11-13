"""Read-only source operations doctor on actual protected WAL custody.

GGUF token generation is SYNTHETIC; this suite never loads model files.
The doctor is exercised from a fresh read-only SQLite authority while its
writer is open, and again after true connection close/cold reopen.
"""
from __future__ import annotations

from hashlib import sha256
from io import StringIO
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.contracts import Scope
from skeleton.jeeves.native_fabric.durable_queue import WorkOrder, DurableNativeQueue
from skeleton.jeeves.native_fabric.delivery_outbox import (
    NativeDeliveryOutbox, receiver_ack,
)
from skeleton.jeeves.native_fabric.telemetry_store import NativeTelemetryStore
from skeleton.jeeves.native_fabric.cold_doctor import (
    NativeColdFabricHold, inspect_native_operations, main,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, SyntheticallyGenerated,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "descriptor-anchored private native SQLite requires Linux")
class TestNativeFabricColdDoctor(unittest.TestCase):
    PROMPT="Private original operator task: prohibit telemetry text disclosure."
    SESSION="doctor_session"
    REQUEST="doctor_request"
    KEY=bytes.fromhex("d1"*32)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)
        self.scope=Scope("local","operator",MODEL,TOKENIZER)
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=self.scope.binding,
            clock_ns=lambda:1000000,
        )
        self.telemetry=NativeTelemetryStore(
            self.worker,clock_ns=lambda:1000000,
        )
        self.outbox=NativeDeliveryOutbox(
            self.queue,receiver_id="laptop_screen",
            receiver_key=self.KEY,clock_ns=lambda:1000000,
        )
        # Creation of the read-only doctor must not depend on an attached
        # backend, license receipt, source index, or loaded GGUF model.
        from skeleton.jeeves.agent.native_durable_batch import NativeDurableBatchConveyor
        self.batch=NativeDurableBatchConveyor(self.worker,approved=True)

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

    def _inspect(self,*,subject="operator",rows=10000):
        return inspect_native_operations(
            state_dir=Path(self.tmp.name),
            tenant="local",subject=subject,
            model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
            maximum_rows=rows,
        )

    def _order(self):
        order=WorkOrder(
            "doctor_order",self.scope.binding,"local","operator",MODEL,TOKENIZER,
            self.SESSION,self.REQUEST,
            sha256(self.PROMPT.encode()).hexdigest(),0,0.8,
            "operator",10,1000000,10000000,
        )
        self.spine.create(self.SESSION)
        self.queue.submit(order)
        return order

    def _commit(self):
        order=self._order()
        claim=self.queue.claim(order.order_id)
        self.queue.execute_claimed(
            claim,prompt=self.PROMPT,operator_approved=True,
        )
        return order

    def _delivery(self):
        order=self._commit()
        self.outbox.prepare(
            delivery_id="doctor_delivery",
            order_id=order.order_id,channel="local_console",
        )
        return order

    def test_empty_source_doctor_is_readonly_and_not_device_certification(self):
        report=self._inspect()
        self.assertEqual(report["work_order_counts"],{})
        self.assertEqual(report["telemetry_samples"],0)
        self.assertFalse(report["model_inference_started"])
        self.assertFalse(report["device_pressure_qualified"])
        self.assertFalse(report["release_certified"])
        self.assertEqual(self.backend.calls,0)

    def test_queued_order_does_not_fabricate_model_result(self):
        self._order()
        report=self._inspect()
        self.assertEqual(report["work_order_counts"]["queued"],1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(report["native_request_counts"],{})

    def test_claimed_order_causes_explicit_unknown_effect_hold(self):
        order=self._order()
        self.queue.claim(order.order_id)
        report=self._inspect()
        self.assertIn("work_unknown_or_claimed",report["holds"])
        self.assertFalse(report["unknown_effects_clear"])
        self.assertEqual(self.backend.calls,0)

    def test_committed_request_is_proved_by_actual_sqlite_transcript(self):
        self._commit()
        report=self._inspect()
        self.assertEqual(report["work_order_counts"]["committed"],1)
        self.assertEqual(report["native_request_counts"]["committed"],1)
        self.assertEqual(report["holds"],[])
        self.assertEqual(self.backend.calls,1)

    def test_pending_delivery_intent_is_held_as_unsent(self):
        self._delivery()
        report=self._inspect()
        self.assertIn("unsent_delivery_intents",report["holds"])
        self.assertEqual(report["delivery_counts"]["pending"],1)

    def test_unconfirmed_delivery_claim_stays_held(self):
        self._delivery()
        self.outbox.claim("doctor_delivery")
        report=self._inspect()
        self.assertIn("delivery_unknown_or_claimed",report["holds"])
        self.assertNotIn("unsent_delivery_intents",report["holds"])

    def test_receiver_hmac_ack_removes_unsent_hold_without_claiming_human_ux(self):
        self._delivery()
        claim=self.outbox.claim("doctor_delivery")
        signature=receiver_ack(
            spec_sha256=claim.intent.fingerprint,
            receiver_id="laptop_screen",receiver_key=self.KEY,
        )
        self.outbox.acknowledge(claim,receiver_hmac=signature)
        report=self._inspect()
        self.assertEqual(report["delivery_counts"]["delivered"],1)
        self.assertEqual(report["holds"],[])
        self.assertFalse(report["release_certified"])

    def test_observation_provenance_checks_canonical_turn(self):
        order=self._commit()
        self.telemetry.record_committed(
            observation_id="doctor_observe",
            session_id=self.SESSION,request_id=self.REQUEST,
            prompt=self.PROMPT,duration_ms=100,
        )
        result=self._inspect()
        self.assertEqual(result["telemetry_samples"],1)
        self.assertNotIn(self.PROMPT,str(result))
        self.assertNotIn(self.backend.answer,str(result))

    def test_corrupt_telemetry_payload_sha_causes_offline_hold(self):
        self._commit()
        self.telemetry.record_committed(
            observation_id="doctor_observe",
            session_id=self.SESSION,request_id=self.REQUEST,
            prompt=self.PROMPT,duration_ms=100,
        )
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_observations SET sample_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeColdFabricHold):
            self._inspect()

    def test_corrupt_work_spec_detected_without_model_activation(self):
        self._order()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_work_orders SET priority=priority+1",
            )
        with self.assertRaises(NativeColdFabricHold):
            self._inspect()
        self.assertEqual(self.backend.calls,0)

    def test_missing_native_committed_receipt_is_held(self):
        self._commit()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM turns")
        with self.assertRaises(NativeColdFabricHold):
            self._inspect()

    def test_changed_native_output_bytes_are_held(self):
        self._commit()
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET response=?", (b"forged!",))
        with self.assertRaises(NativeColdFabricHold):
            self._inspect()

    def test_delivery_cannot_outlive_its_work_receipt_identity(self):
        self._delivery()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_delivery_intents "
                "SET work_receipt_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeColdFabricHold):
            self._inspect()

    def test_unapproved_native_request_exception_is_visible_as_uncertain(self):
        self._order()
        self.backend.fail=True
        with self.assertRaises(RuntimeError):
            self.worker.turn(self.SESSION,self.REQUEST,self.PROMPT)
        report=self._inspect()
        self.assertIn("native_inference_uncertain",report["holds"])
        self.assertEqual(report["native_request_counts"]["pending"],1)

    def test_readonly_inspection_remains_possible_when_native_worker_is_closed(self):
        self._commit()
        self._close()
        report=self._inspect()
        self.assertEqual(report["work_order_counts"]["committed"],1)
        self.assertEqual(report["native_request_counts"]["committed"],1)

    def test_foreign_subject_cannot_inspect_others_work(self):
        self._commit()
        # This is an operator-isolated inventory; foreign principals see no
        # work IDs, model text, source paths or private user records.
        foreign=self._inspect(subject="foreign")
        self.assertEqual(foreign["work_order_counts"],{})
        self.assertEqual(foreign["telemetry_samples"],0)

    def test_invalid_relative_or_parent_walk_state_root_is_refused(self):
        for path in (Path("relative"),Path("/tmp/../tmp")):
            with self.subTest(path=str(path)),self.assertRaises(NativeColdFabricHold):
                inspect_native_operations(
                    state_dir=path,tenant="local",subject="operator",
                    model_sha256=MODEL,tokenizer_sha256=TOKENIZER,
                )

    def test_operator_can_limit_audit_inventory_finite_ceiling(self):
        self._order()
        with self.assertRaises(NativeColdFabricHold):
            self._inspect(rows=0)

    def test_real_readonly_audit_does_not_change_sqlite_revision(self):
        self._commit()
        with self.db.snapshot() as conn:
            before=conn.execute(
                "SELECT revision FROM sessions WHERE session=?",
                (self.SESSION,),
            ).fetchone()[0]
        self._inspect()
        with self.db.snapshot() as conn:
            after=conn.execute(
                "SELECT revision FROM sessions WHERE session=?",
                (self.SESSION,),
            ).fetchone()[0]
        self.assertEqual(before,after)

    def test_cli_reports_hold_without_private_prompt_disclosure(self):
        self._delivery()
        output,errors=StringIO(),StringIO()
        argv=[
            "--state-dir",self.tmp.name,
            "--tenant","local","--subject","operator",
            "--model-sha256",MODEL,"--tokenizer-sha256",TOKENIZER,
        ]
        with mock.patch("sys.stdout",output),mock.patch("sys.stderr",errors):
            code=main(argv)
        self.assertEqual(code,3,errors.getvalue())
        self.assertIn("unsent_delivery_intents",output.getvalue())
        self.assertNotIn(self.PROMPT,output.getvalue())
        self.assertNotIn(self.PROMPT,errors.getvalue())

    def test_cli_invalid_path_does_not_expose_path_or_query_text(self):
        out,err=StringIO(),StringIO()
        argv=[
            "--state-dir","relative-doctor-state",
            "--tenant","local","--subject","operator",
            "--model-sha256",MODEL,"--tokenizer-sha256",TOKENIZER,
        ]
        with mock.patch("sys.stdout",out),mock.patch("sys.stderr",err):
            code=main(argv)
        self.assertEqual(code,2)
        self.assertNotIn("relative-doctor-state",err.getvalue())


if __name__=="__main__":
    unittest.main()
