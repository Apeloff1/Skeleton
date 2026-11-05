"""Native durable checkpoint custody over the REAL protected SQLite implementation.

The backend in adjacent agent integration suites is SYNTHETIC. No GGUF,
Windows device, rights or native cancellation certification is inferred.
"""
from __future__ import annotations

from dataclasses import replace
import json
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
from skeleton.jeeves.agent.native_checkpoint_journal import (
    NativeCheckpointHold, NativeSQLiteCheckpointer,
)
from skeleton.jeeves.agent.runtime import RunCheckpoint, RunInputs
from skeleton.jeeves.agent.types import AgentPhase, Budget, Goal, Usage
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ScriptedAgentBackend,
)


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "protected native SQLite requires Linux /proc")
class TestNativeCheckpointJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = None
        self.gate = None
        self._open()
        self.addCleanup(self._close)
        self.inputs = self._inputs()

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate = None
        if self.db is not None:
            self.db.close()
            self.db = None

    def _open(self, tenant="local", subject="operator"):
        self.db = SpineDatabase(self.tmp.name)
        self.gate = SessionGate(self.tmp.name)
        self.backend = ScriptedAgentBackend()
        spine = ExecutionSpine(
            db=self.db, session_gate=self.gate, backend=self.backend,
            identity=Identity(tenant, subject, MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        )
        self.worker = SupervisedAI(spine)

    def _cold(self, tenant="local", subject="operator"):
        self._close()
        self._open(tenant, subject)

    def _inputs(self, *, objective="Bounded reasoning", run_id="durable_test_run"):
        return RunInputs(
            goal=Goal("durable_goal", objective),
            tenant_id="local", user_id="operator", run_id=run_id,
            preferred_provider="jeeves_native",
            budget=Budget(max_steps=8, max_model_calls=8,
                          max_tool_calls=1, max_tokens=16000,
                          max_wall_seconds=120),
        )

    def _ckpt(self, number=1, *, phase=AgentPhase.CREATED):
        return RunCheckpoint(
            run_id=self.inputs.run_id, goal_id=self.inputs.goal.goal_id,
            phase=phase, sequence=number, usage=Usage(),
            metadata={"tenant_id": "local", "user_id": "operator",
                      "workspace_id": "default"},
        )

    def _claimed(self, **limits):
        store = NativeSQLiteCheckpointer(self.worker, **limits)
        store.create_run(self.inputs)
        return store

    def test_append_round_trip_via_real_sqlite_and_codec(self):
        store = self._claimed()
        checkpoint = self._ckpt()
        self.assertIs(store.save(checkpoint), checkpoint)
        self.assertEqual(store.latest(self.inputs.run_id).fingerprint,
                         checkpoint.fingerprint)
        self.assertEqual(store.history(self.inputs.run_id)[0].phase,
                         AgentPhase.CREATED)

    def test_owner_bound_cold_reopen_retains_checkpoint_chain(self):
        store = self._claimed()
        store.save(self._ckpt(1))
        store.save(self._ckpt(2, phase=AgentPhase.PLANNING))
        self._cold()
        fresh = NativeSQLiteCheckpointer(self.worker)
        fresh.bind_existing(self.inputs)
        self.assertEqual([x.sequence for x in fresh.history(self.inputs.run_id)],
                         [1, 2])
        self.assertEqual(fresh.inspect(self.inputs.run_id)["phase"], "planning")

    def test_duplicate_claim_is_never_rerun_permission(self):
        store = self._claimed()
        with self.assertRaises(NativeCheckpointHold):
            store.create_run(self.inputs)

    def test_changed_objective_invalidates_same_run_id(self):
        store = self._claimed()
        with self.assertRaises(NativeCheckpointHold):
            store.bind_existing(self._inputs(objective="changed task"))
        self.assertIsNone(store.latest(self.inputs.run_id))

    def test_missing_run_is_not_implicitly_created_by_resume(self):
        store = NativeSQLiteCheckpointer(self.worker)
        with self.assertRaises(NativeCheckpointHold):
            store.bind_existing(self.inputs)
        self.assertEqual(store.runs(), ())

    def test_model_and_subject_bound_across_cold_reopen(self):
        store = self._claimed()
        store.save(self._ckpt())
        self._cold(subject="different")
        foreign = NativeSQLiteCheckpointer(self.worker)
        with self.assertRaises(NativeCheckpointHold):
            foreign.latest(self.inputs.run_id)
        with self.assertRaises(NativeCheckpointHold):
            foreign.bind_existing(self.inputs)

    def test_checkpoint_cannot_skip_or_repeat_sequence(self):
        store = self._claimed()
        with self.assertRaises(NativeCheckpointHold):
            store.save(self._ckpt(2))
        store.save(self._ckpt(1))
        with self.assertRaises(NativeCheckpointHold):
            store.save(self._ckpt(1))
        with self.assertRaises(NativeCheckpointHold):
            store.save(self._ckpt(3))
        self.assertEqual(store.latest(self.inputs.run_id).sequence, 1)

    def test_payload_tamper_is_detected_before_read_or_next_write(self):
        store = self._claimed()
        store.save(self._ckpt())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_checkpoints SET payload=? WHERE run_id=?",
                (b'{"not":"trusted"}', self.inputs.run_id),
            )
        with self.assertRaises(NativeCheckpointHold):
            store.latest(self.inputs.run_id)
        with self.assertRaises(NativeCheckpointHold):
            store.save(self._ckpt(2))

    def test_entry_hash_tamper_is_detected(self):
        store = self._claimed()
        store.save(self._ckpt())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_checkpoints SET entry_hash=? WHERE run_id=?",
                ("f" * 64, self.inputs.run_id),
            )
        with self.assertRaises(NativeCheckpointHold):
            store.history(self.inputs.run_id)

    def test_tip_hash_tamper_is_detected(self):
        store = self._claimed()
        store.save(self._ckpt())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_runs SET tip_hash=? WHERE run_id=?",
                ("f" * 64, self.inputs.run_id),
            )
        with self.assertRaises(NativeCheckpointHold):
            store.latest(self.inputs.run_id)

    def test_truncated_sqlite_checkpoint_row_fails_closed(self):
        store = self._claimed()
        store.save(self._ckpt())
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM jeeves_native_checkpoints WHERE run_id=?",
                (self.inputs.run_id,),
            )
        with self.assertRaises(NativeCheckpointHold):
            store.history(self.inputs.run_id)

    def test_retention_preserves_attested_anchor_sequence(self):
        store = self._claimed(max_versions_per_run=2)
        for number in range(1, 5):
            store.save(self._ckpt(number))
        self.assertEqual([x.sequence for x in store.history(self.inputs.run_id)],
                         [3, 4])
        with self.db.snapshot() as conn:
            row = conn.execute(
                "SELECT anchor_sequence FROM jeeves_native_runs WHERE run_id=?",
                (self.inputs.run_id,),
            ).fetchone()
        self.assertEqual(row, (2,))

    def test_retention_anchor_tamper_fails(self):
        store = self._claimed(max_versions_per_run=1)
        store.save(self._ckpt(1))
        store.save(self._ckpt(2))
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_runs SET anchor_hash=? WHERE run_id=?",
                ("e" * 64, self.inputs.run_id),
            )
        with self.assertRaises(NativeCheckpointHold):
            store.latest(self.inputs.run_id)

    def test_native_intent_fences_crash_before_checkpoint(self):
        store = self._claimed()
        store.save(self._ckpt())
        store.begin_native_call(self.inputs.run_id, 1)
        self._cold()
        fresh = NativeSQLiteCheckpointer(self.worker)
        self.assertTrue(fresh.has_inflight(self.inputs.run_id))
        with self.assertRaises(NativeCheckpointHold):
            fresh.assert_no_inflight(self.inputs.run_id)
        with self.assertRaises(NativeCheckpointHold):
            fresh.begin_native_call(self.inputs.run_id, 1)

    def test_model_intent_requires_advanced_checkpoint_to_clear(self):
        store = self._claimed()
        store.save(self._ckpt(1))
        store.begin_native_call(self.inputs.run_id, 1)
        with self.assertRaises(NativeCheckpointHold):
            store.complete_native_call(self.inputs.run_id)
        store.save(self._ckpt(2))
        store.complete_native_call(self.inputs.run_id)
        store.assert_no_inflight(self.inputs.run_id)
        self.assertFalse(store.has_inflight(self.inputs.run_id))

    def test_duplicate_intent_without_clear_cannot_enter_model(self):
        store = self._claimed()
        store.save(self._ckpt())
        store.begin_native_call(self.inputs.run_id, 1)
        with self.assertRaises(NativeCheckpointHold):
            store.begin_native_call(self.inputs.run_id, 1)

    def test_completed_intent_does_not_confuse_next_model_call(self):
        store = self._claimed()
        store.save(self._ckpt(1))
        store.begin_native_call(self.inputs.run_id, 1)
        store.save(self._ckpt(2))
        store.complete_native_call(self.inputs.run_id)
        store.begin_native_call(self.inputs.run_id, 2)
        self.assertTrue(store.has_inflight(self.inputs.run_id))

    def test_public_inspection_does_not_disclose_private_task(self):
        store = self._claimed()
        store.save(self._ckpt())
        result = store.inspect(self.inputs.run_id)
        self.assertEqual(result["phase"], "created")
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["release_certified"])
        self.assertNotIn(self.inputs.goal.objective, json.dumps(result))

    def test_terminal_result_absent_on_newly_claimed_run(self):
        store = self._claimed()
        self.assertIsNone(store.terminal_result(self.inputs.run_id))
        self.assertFalse(store.inspect(self.inputs.run_id)["terminal_result_saved"])

    def test_terminal_result_for_unknown_run_is_not_disclosed(self):
        store = NativeSQLiteCheckpointer(self.worker)
        with self.assertRaises(NativeCheckpointHold):
            store.terminal_result("unknown_run")

    def test_clear_is_denied_because_it_erases_replay_custody(self):
        store = self._claimed()
        with self.assertRaises(NativeCheckpointHold):
            store.clear(self.inputs.run_id)

    def test_capacity_is_fail_closed_before_new_run(self):
        store = self._claimed(max_runs=1)
        with self.assertRaises(NativeCheckpointHold):
            store.create_run(self._inputs(run_id="second_run"))

    def test_invalid_retention_limits_cannot_be_bypassed_with_bool(self):
        for value in (0, True, -1, 100000):
            with self.subTest(value=value), self.assertRaises(NativeCheckpointHold):
                NativeSQLiteCheckpointer(
                    self.worker, max_versions_per_run=value,
                )


if __name__ == "__main__":
    unittest.main()
