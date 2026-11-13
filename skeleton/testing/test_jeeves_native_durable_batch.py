"""Exact native batch custody with real SQLite and synthetic generator.

All side-effect fencing, operator binding, deterministic session IDs,
native receipts, model replay, queue CAS and telemetry use actual production
modules. A scripted test generator stands in for real licensed GGUF weights;
none of these source checks qualify device pressure, real-model accuracy or
release readiness.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_batch_runtime import NativeBatchTask,NativeBatchPolicy
from skeleton.jeeves.agent.native_fabric_supervisor import FabricJob
from skeleton.jeeves.agent.native_durable_batch import (
    NativeDurableBatchConveyor,NativeDurableBatchHold,
)
from skeleton.jeeves.native_fabric.durable_queue import DurableQueueHold
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "production native SQLite requires Linux")
class TestDurableNativeBatch(unittest.TestCase):
    BATCH="source_approved_batch"
    TASK_A="Original offline reasoning task A."
    TASK_B="Original offline reasoning task B."

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=None
        self.gate=None
        self.time_ns=[1700000000000000000]
        self._open()
        self.addCleanup(self._close)
        self.jobs=self._jobs()

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _open(self,*,subject="operator",backend=None):
        self.db=SpineDatabase(self.temp.name)
        self.gate=SessionGate(self.temp.name)
        self.backend=backend or SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        )
        self.worker=SupervisedAI(self.spine)
        self.conveyor=NativeDurableBatchConveyor(
            self.worker,approved=True,
            clock_ns=lambda:self.time_ns[0],
        )

    def _cold(self,*,subject="operator",backend=None):
        self._close()
        self._open(subject=subject,backend=backend)

    def _jobs(self):
        return (
            FabricJob(NativeBatchTask("job_a",self.TASK_A),
                      cohort="frontier",priority=10),
            FabricJob(NativeBatchTask("job_b",self.TASK_B),
                      cohort="operations",priority=3),
        )

    def _admit(self,jobs=None):
        return self.conveyor.admit(self.BATCH,jobs or self.jobs)

    def _status(self,jobs=None):
        return self.conveyor.inspect(self.BATCH,jobs or self.jobs)

    def test_native_batch_admission_is_nonexecuting(self):
        status=self._admit()
        self.assertEqual(status.total,2)
        self.assertEqual(status.ready,2)
        self.assertEqual(status.committed,0)
        self.assertFalse(status.complete)
        self.assertEqual(self.backend.calls,0)

    def test_one_bounded_execution_wave_commits_one_real_sqlite_receipt(self):
        self._admit()
        result=self.conveyor.execute_admitted(
            self.BATCH,self.jobs,maximum_new_calls=1,
        )
        self.assertEqual(result["processed"],1)
        self.assertEqual(self.backend.calls,1)
        status=self._status()
        self.assertEqual(status.ready,1)
        self.assertEqual(status.committed,1)
        self.assertFalse(status.complete)
        self.assertEqual(self.conveyor.telemetry.summarize()["observations"],1)

    def test_second_wave_completes_without_replaying_first_model_call(self):
        self._admit()
        self.conveyor.execute_admitted(self.BATCH,self.jobs)
        final=self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self.assertEqual(final["processed"],1)
        self.assertEqual(self.backend.calls,2)
        self.assertTrue(self._status().complete)

    def test_no_model_calls_on_completed_batch_reinspection(self):
        self._admit()
        self.conveyor.execute_admitted(
            self.BATCH,self.jobs,maximum_new_calls=2,
        )
        outcome=self.conveyor.execute_admitted(
            self.BATCH,self.jobs,maximum_new_calls=2,
        )
        self.assertEqual(outcome["processed"],0)
        self.assertEqual(self.backend.calls,2)

    def test_cold_reopen_preserves_committed_queue_and_telemetry(self):
        self._admit()
        self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self._cold()
        status=self._status()
        self.assertEqual(status.committed,1)
        self.assertEqual(status.ready,1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.conveyor.telemetry.summarize()["observations"],1)

    def test_cold_reopen_can_complete_only_remaining_queued_job(self):
        self._admit()
        self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self._cold()
        result=self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self.assertEqual(result["processed"],1)
        self.assertEqual(self.backend.calls,1)
        self.assertTrue(self._status().complete)

    def test_atomic_batch_admission_rolls_back_header_and_any_preceding_rows(self):
        from unittest import mock
        original=self.conveyor.queue._insert_many
        def interrupt_after_one(conn,orders):
            original(conn,orders[:1])
            raise KeyboardInterrupt()
        with mock.patch.object(
            self.conveyor.queue,"_insert_many",
            side_effect=interrupt_after_one,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self._admit()
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_durable_batches",
            ).fetchone(),(0,))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_work_orders",
            ).fetchone(),(0,))
        self.assertEqual(self.backend.calls,0)
        # A clean retry can admit precisely the same approved batch because
        # the failed transaction never published an intent or native effect.
        fresh=self._admit()
        self.assertEqual(fresh.ready,2)

    def test_work_order_bulk_admission_has_no_intermediate_committed_header(self):
        report=self._admit()
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT state FROM jeeves_native_durable_batches",
                ).fetchone(),("ready",),
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM jeeves_native_work_orders",
                ).fetchone(),(2,),
            )
        self.assertEqual(report.total,2)

    def test_duplicate_batch_identity_cannot_start_again(self):
        self._admit()
        with self.assertRaises(NativeDurableBatchHold):
            self._admit()
        self.assertEqual(self.backend.calls,0)

    def test_altered_task_under_same_batch_id_is_denied(self):
        self._admit()
        swapped=(FabricJob(NativeBatchTask("job_a","Changed task")),
                 self.jobs[1])
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.execute_admitted(self.BATCH,swapped)
        self.assertEqual(self.backend.calls,0)

    def test_priority_rewriting_after_admission_is_denied(self):
        self._admit()
        switched=(replace(self.jobs[0],priority=0),self.jobs[1])
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.execute_admitted(self.BATCH,switched)

    def test_cohort_rewriting_after_admission_is_denied(self):
        self._admit()
        switched=(replace(self.jobs[0],cohort="other"),self.jobs[1])
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.inspect(self.BATCH,switched)

    def test_task_inventory_reordering_after_admission_is_denied(self):
        self._admit()
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.inspect(self.BATCH,tuple(reversed(self.jobs)))

    def test_missing_operator_approval_refuses_batch_conveyor(self):
        with self.assertRaises(NativeDurableBatchHold):
            NativeDurableBatchConveyor(self.worker,approved=False)

    def test_foreign_principal_cannot_inspect_batch_or_generate(self):
        self._admit()
        self._cold(subject="foreign")
        with self.assertRaises(NativeDurableBatchHold):
            self._status()
        self.assertEqual(self.backend.calls,0)

    def test_crash_after_native_commit_before_queue_reconciliation(self):
        self._admit()
        order_id=self.conveyor._order_key(self.BATCH,"job_a")
        claim=self.conveyor.queue.claim(order_id)
        # This represents an actual native turn finishing while queue commit
        # was interrupted. The real SQLite receipt is already authoritative.
        self.spine.create(claim.order.session_id)
        self.worker.turn(claim.order.session_id,claim.order.request_id,
                         self.TASK_A,seed=0,temperature=0.8)
        self.assertEqual(self.backend.calls,1)
        self._cold()
        observed=self._status()
        self.assertEqual(observed.claimed,1)
        result=self.conveyor.reconcile_orphans(
            self.BATCH,self.jobs,operator_approved=True,
        )
        self.assertEqual(result["reconciled"],1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self._status().committed,1)

    def test_missing_native_effect_cannot_be_reconciled_or_reissued(self):
        self._admit()
        order_id=self.conveyor._order_key(self.BATCH,"job_a")
        self.conveyor.queue.claim(order_id)
        self._cold()
        with self.assertRaises(DurableQueueHold):
            self.conveyor.reconcile_orphans(
                self.BATCH,self.jobs,operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self._status().claimed,1)

    def test_orphan_recovery_requires_explicit_operator_approval(self):
        self._admit()
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.reconcile_orphans(
                self.BATCH,self.jobs,operator_approved=False,
            )

    def test_synthetic_generation_failure_leaves_claim_held(self):
        self.backend.fail=True
        self._admit()
        with self.assertRaises(RuntimeError):
            self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self._status().claimed,1)
        self._cold()
        with self.assertRaises(DurableQueueHold):
            self.conveyor.reconcile_orphans(
                self.BATCH,self.jobs,operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_batch_report_contains_no_private_prompt_data(self):
        result=self._admit().to_public_record()
        self.assertNotIn(self.TASK_A,str(result))
        self.assertNotIn(self.TASK_B,str(result))
        self.assertFalse(result["release_certified"])
        self.assertFalse(result["actual_device_qualified"])

    def test_source_only_policy_never_claims_real_gguf_proof(self):
        self._admit()
        report=self._status().to_public_record()
        self.assertFalse(report["model_rights_independently_verified"])

    def test_model_requirement_rejects_wrong_type_and_empty_batch(self):
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.admit(self.BATCH,())
        with self.assertRaises(NativeDurableBatchHold):
            self.conveyor.admit(self.BATCH,("untyped",))

    def test_pending_crash_does_not_repopulate_automatic_queue(self):
        self._admit()
        first=self.conveyor._order_key(self.BATCH,"job_a")
        self.conveyor.queue.claim(first)
        self._cold()
        response=self.conveyor.execute_admitted(self.BATCH,self.jobs)
        self.assertEqual(response["processed"],1)
        self.assertEqual(self._status().claimed,1)
        self.assertEqual(self._status().committed,1)
        self.assertEqual(self.backend.calls,1)


if __name__=="__main__":
    unittest.main()
