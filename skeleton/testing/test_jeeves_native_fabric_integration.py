"""Integrated native fabric: real canonical SQLite and synthetic-only generation.

Checks the end-to-end admitted work path: scope, fair traffic, conservation,
audited event commitments and canonical WAL/SQLite idempotent replay.
NO physical GGUF or Windows/WSL2 inference is executed in this suite.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits, Conflict, Busy, IntegrityFailure,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_batch_runtime import NativeBatchTask, NativeBatchHold
from skeleton.jeeves.agent.native_fabric_supervisor import (
    FabricJob, FabricRunPolicy, NativeFabricHold, NativeFabricSupervisor,
)
from skeleton.jeeves.native_fabric.contracts import ContractHold
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ANSWER, SyntheticallyGenerated,
)


def jobs(count: int, *, cohort="alpha", descending=False):
    return tuple(
        FabricJob(
            task=NativeBatchTask(
                task_id=f"fabric_{index:02d}",
                prompt=f"Host-approved bounded reasoning task {index}",
            ),
            cohort=cohort,
            priority=100 - index if descending else index,
        )
        for index in range(count)
    )


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "protected SQLite descriptor custody requires Linux")
class TestNativeFabricIntegrated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = None
        self.gate = None
        self._open()
        self.addCleanup(self._close)

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate = None
        if self.db is not None:
            self.db.close()
            self.db = None

    def _open(self, *, subject="operator"):
        self.db = SpineDatabase(self.tmp.name)
        self.gate = SessionGate(self.tmp.name)
        self.backend = SyntheticallyGenerated()
        self.worker = SupervisedAI(ExecutionSpine(
            db=self.db, session_gate=self.gate, backend=self.backend,
            identity=Identity("local", subject, MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        ))

    def _cold(self, *, subject="operator"):
        self._close()
        self._open(subject=subject)

    def _fabric(self, **kwargs):
        return NativeFabricSupervisor(self.worker, approved=True, **kwargs)

    def test_two_jobs_commit_and_conserve_budget(self):
        result = self._fabric().run("fabric_batch", jobs(2))
        self.assertEqual(len(result.ordered_results), 2)
        self.assertEqual(self.backend.calls, 2)
        self.assertEqual(result.auxiliary_event_count, 4)
        self.assertEqual(result.auxiliary_traffic_snapshot["counts"]["committed"], 2)
        self.assertEqual(result.auxiliary_budget_snapshot["committed"], 2)
        self.assertEqual(result.auxiliary_budget_snapshot["held"], 0)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (2,))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox").fetchone(), (2,))

    def test_unused_resource_tokens_are_released_after_receipt(self):
        result = self._fabric().run("fabric_batch", jobs(2))
        budget = result.auxiliary_budget_snapshot
        self.assertEqual(budget["ceiling"]["inference_calls"], 2)
        self.assertEqual(budget["available"]["inference_calls"], 0)
        self.assertGreater(budget["available"]["output_tokens"], 0)
        self.assertGreater(budget["available"]["bytes_written"], 0)

    def test_cold_epoch_replays_sqlite_without_model_generation(self):
        first = self._fabric().run("fabric_batch", jobs(2))
        self.assertEqual(self.backend.calls, 2)
        self._cold()
        second = self._fabric().run("fabric_batch", jobs(2))
        self.assertEqual(self.backend.calls, 0)
        self.assertTrue(all(x.batch_receipt.replayed for x in second.ordered_results))
        self.assertEqual(
            [x.batch_receipt.output_sha256 for x in first.ordered_results],
            [x.batch_receipt.output_sha256 for x in second.ordered_results],
        )
        self.assertEqual(
            second.auxiliary_budget_snapshot["available"]["inference_calls"], 2,
        )

    def test_same_supervisor_cannot_reset_admission_epoch(self):
        fabric = self._fabric()
        fabric.run("fabric_batch", jobs(1))
        with self.assertRaises(NativeFabricHold):
            fabric.run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 1)

    def test_explicit_operator_approval_is_required(self):
        with self.assertRaises(NativeFabricHold):
            NativeFabricSupervisor(self.worker, approved=False)
        self.assertEqual(self.backend.calls, 0)

    def test_priority_in_same_cohort_preserves_declared_order(self):
        items = jobs(3, descending=True)
        result = self._fabric().run("fabric_batch", items)
        self.assertEqual(
            [x.task_id for x in result.ordered_results],
            [item.task.task_id for item in items],
        )

    def test_priority_reorders_independent_jobs_without_new_ids(self):
        items = jobs(3)
        result = self._fabric().run("fabric_batch", items)
        self.assertEqual(
            [x.task_id for x in result.ordered_results],
            ["fabric_02", "fabric_01", "fabric_00"],
        )
        self._cold()
        replay = self._fabric().run("fabric_batch", items)
        self.assertEqual(
            [x.task_id for x in replay.ordered_results],
            [x.task_id for x in result.ordered_results],
        )
        self.assertEqual(self.backend.calls, 0)

    def test_round_robin_cohorts_before_native_execution(self):
        original = (
            FabricJob(NativeBatchTask("a1", "Alpha one"), cohort="alpha"),
            FabricJob(NativeBatchTask("a2", "Alpha two"), cohort="alpha"),
            FabricJob(NativeBatchTask("b1", "Beta one"), cohort="beta"),
            FabricJob(NativeBatchTask("b2", "Beta two"), cohort="beta"),
        )
        result = self._fabric().run("fabric_batch", original)
        self.assertEqual(
            [x.task_id for x in result.ordered_results],
            ["a1", "b1", "a2", "b2"],
        )

    def test_native_receipts_match_approved_model_and_scope(self):
        result = self._fabric().run("fabric_batch", jobs(2))
        for item in result.ordered_results:
            proof = item.to_record()
            self.assertEqual(proof["native"]["model_sha256"], MODEL)
            self.assertEqual(proof["native"]["tokenizer_sha256"], TOKENIZER)
            self.assertEqual(
                proof["traffic_receipt_sha256"], proof["native"]["output_sha256"],
            )

    def test_host_fabric_cannot_grant_native_tools(self):
        result = self._fabric().run("fabric_batch", jobs(3))
        self.assertEqual(
            result.auxiliary_budget_snapshot["ceiling"]["tool_calls"], 0,
        )
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM effects").fetchone(), (0,))

    def test_unknown_native_effect_persists_across_cold_restart(self):
        self.backend.fail = True
        with self.assertRaises(RuntimeError):
            self._fabric().run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT state FROM requests").fetchone(), ("pending",),
            )
        self._cold()
        with self.assertRaises(Busy):
            self._fabric().run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 0)

    def test_tampered_response_is_not_replayed_or_regenerated(self):
        self._fabric().run("fabric_batch", jobs(1))
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET response=?", (b"tampered",))
        self._cold()
        with self.assertRaises(IntegrityFailure):
            self._fabric().run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 0)

    def test_changed_prompt_same_task_id_blocks_native_regeneration(self):
        self._fabric().run("fabric_batch", jobs(1))
        self._cold()
        changed = (FabricJob(NativeBatchTask("fabric_00", "Changed task bytes")),)
        with self.assertRaises(Conflict):
            self._fabric().run("fabric_batch", changed)
        self.assertEqual(self.backend.calls, 0)

    def test_duplicate_job_id_refused_before_any_model(self):
        item = jobs(1)[0]
        with self.assertRaises(NativeFabricHold):
            self._fabric().run("fabric_batch", (item, item))
        self.assertEqual(self.backend.calls, 0)

    def test_resource_reservation_checked_before_native_model(self):
        policy = FabricRunPolicy(maximum_total_reserved_output_tokens=100)
        with self.assertRaises(NativeBatchHold):
            self._fabric(policy=policy).run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 0)

    def test_unbounded_cohorts_refused_before_native_generation(self):
        items = (
            FabricJob(NativeBatchTask("a", "Task alpha"), cohort="alpha"),
            FabricJob(NativeBatchTask("b", "Task beta"), cohort="beta"),
        )
        policy = FabricRunPolicy(maximum_cohorts=1)
        with self.assertRaises(NativeFabricHold):
            self._fabric(policy=policy).run("fabric_batch", items)
        self.assertEqual(self.backend.calls, 0)

    def test_invalid_priority_is_refused_preinference(self):
        for value in (True, -1, 1001, "five"):
            with self.subTest(value=value), self.assertRaises(ContractHold):
                FabricJob(NativeBatchTask("item", "Task"), priority=value)

    def test_multiple_native_lanes_require_hardware_qualification(self):
        with self.assertRaises(NativeFabricHold):
            self._fabric(policy=FabricRunPolicy(
                maximum_active_native=2, maximum_per_scope=1,
            ))
        self.assertEqual(self.backend.calls, 0)

    def test_unknown_extra_host_capability_cannot_be_submitted(self):
        with self.assertRaises(TypeError):
            FabricJob(NativeBatchTask("item", "Task"), permission="shell")

    def test_full_result_does_not_reveal_prompt_or_model_answer(self):
        result = self._fabric().run("fabric_batch", jobs(1))
        public = json.dumps(result.to_record())
        self.assertNotIn("Host-approved bounded reasoning task", public)
        self.assertNotIn(ANSWER, public)
        self.assertFalse(result.to_record()["release_certified"])
        self.assertFalse(result.to_record()["physical_gguf_qualified"])

    def test_native_result_is_single_authority_even_with_host_audit(self):
        result = self._fabric().run("fabric_batch", jobs(3))
        self.assertTrue(result.to_record()["native_sqlite_is_only_effect_authority"])
        self.assertFalse(result.to_record()["auxiliary_journals_restart_safe"])
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (3,))

    def test_event_root_changes_when_workload_size_changes(self):
        first = self._fabric().run("fabric_batch_1", jobs(1))
        second = self._fabric().run("fabric_batch_2", jobs(2))
        self.assertNotEqual(first.auxiliary_event_root, second.auxiliary_event_root)

    def test_wall_timeout_refuses_new_admission(self):
        clock = [10.0]
        fabric = self._fabric(monotonic=lambda: clock[0])
        clock[0] = 1900.0
        # A preflight clock is captured at run entry; we must force an
        # elapsed budget via a deterministic clock callable.
        values = iter([0.0, 1900.0])
        fabric = self._fabric(monotonic=lambda: next(values))
        with self.assertRaises(NativeFabricHold):
            fabric.run("fabric_batch", jobs(1))
        self.assertEqual(self.backend.calls, 0)

    def test_invalid_policy_maximum_events_for_job_limit_is_held(self):
        with self.assertRaises(NativeFabricHold):
            FabricRunPolicy(maximum_jobs=64, maximum_events=100)

    def test_insufficient_queue_capacity_fails_before_any_native_generation(self):
        with self.assertRaises(NativeFabricHold):
            FabricRunPolicy(maximum_jobs=64, maximum_pending=1)

    def test_repeated_model_request_is_only_replayed_on_authoritative_commit(self):
        first = self._fabric().run("fabric_batch", jobs(1))
        self._cold()
        second = self._fabric().run("fabric_batch", jobs(1))
        self.assertEqual(second.to_record()["committed"], 0)
        self.assertEqual(second.to_record()["replayed"], 1)
        self.assertEqual(self.backend.calls, 0)


if __name__ == "__main__":
    unittest.main()
