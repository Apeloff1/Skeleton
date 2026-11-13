"""Protected run-bound working memory, SQLite integrity and cold rehydration.

All tests execute production memory and SQLite code; the model backend used
for integrated planner flows is synthetic and must not be called device proof.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
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
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.native_checkpoint_journal import (
    NativeCheckpointHold, NativeSQLiteCheckpointer,
)
from skeleton.jeeves.agent.native_durable_runtime import NativeDurableJeevesAgent
from skeleton.jeeves.agent.native_run_memory import (
    NativeMemoryHold, NativeRunMemoryStore,
)
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import Budget, Goal, MemoryKind
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ScriptedAgentBackend,
)


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "protected native SQLite requires Linux /proc")
class TestNativeRunScopedMemory(unittest.TestCase):
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

    def _open(self, *, subject="operator"):
        self.db = SpineDatabase(self.tmp.name)
        self.gate = SessionGate(self.tmp.name)
        self.backend = ScriptedAgentBackend()
        spine = ExecutionSpine(
            db=self.db, session_gate=self.gate,
            backend=self.backend,
            identity=Identity("local", subject, MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        )
        self.worker = SupervisedAI(spine)

    def _cold(self, *, subject="operator"):
        self._close()
        self._open(subject=subject)

    def _inputs(self, *, text="Protected memory task", run_id="memory_run_001"):
        return RunInputs(
            goal=Goal("memory_goal", text),
            tenant_id="local", user_id="operator",
            run_id=run_id, preferred_provider="jeeves_native",
            budget=Budget(
                max_steps=8, max_model_calls=8, max_tool_calls=1,
                max_tokens=16384, max_wall_seconds=120,
            ),
        )

    def _store(self, *, capacity=256):
        journal = NativeSQLiteCheckpointer(self.worker)
        journal.create_run(self.inputs)
        return NativeRunMemoryStore(journal, self.inputs, max_records=capacity)

    def _remember(self, store, text="Private reasoning datum", **kwargs):
        return MemoryManager(store=store).remember(
            self.inputs.namespace, text,
            source="reasoning", trust=0.75, salience=0.7,
            tags=("run",), **kwargs,
        )

    def test_native_sqlite_memory_round_trip_and_fingerprint(self):
        store = self._store()
        record = self._remember(store)
        self.assertEqual(store.get(record.memory_id), record)
        self.assertEqual(store.persisted_records, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_memories",
            ).fetchone(), (1,))

    def test_cold_reopen_restores_content_provenance_and_expiry(self):
        store = self._store()
        record = self._remember(
            store, "Authenticated local reasoning",
            ttl_seconds=3600,
        )
        self._cold()
        restored = NativeRunMemoryStore(
            NativeSQLiteCheckpointer(self.worker), self.inputs,
        )
        loaded = restored.get(record.memory_id)
        self.assertEqual(loaded.content, record.content)
        self.assertEqual(loaded.fingerprint, record.fingerprint)
        self.assertEqual(loaded.expires_at, record.expires_at)
        self.assertEqual(loaded.tags, record.tags)
        self.assertEqual(self.backend.calls, 0)

    def test_recall_touch_count_is_committed_and_restored(self):
        store = self._store()
        original = self._remember(store, "needle confidential reasoning token")
        memory = MemoryManager(store=store)
        hits = memory.recall(self.inputs.namespace, "needle", limit=8)
        self.assertTrue(hits)
        updated = store.get(original.memory_id)
        self.assertGreaterEqual(updated.access_count, 1)
        self._cold()
        fresh = NativeRunMemoryStore(
            NativeSQLiteCheckpointer(self.worker), self.inputs,
        )
        self.assertEqual(
            fresh.get(original.memory_id).access_count,
            updated.access_count,
        )

    def test_memory_payload_bitflip_is_held_before_rehydration(self):
        store = self._store()
        self._remember(store)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET payload=?",
                (b'{"tampered":true}',),
            )
        self._cold()
        with self.assertRaises(NativeMemoryHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
            )
        self.assertEqual(self.backend.calls, 0)

    def test_memory_checksum_bitflip_is_held(self):
        store = self._store()
        self._remember(store)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET payload_sha256=?",
                ("f" * 64,),
            )
        with self.assertRaises(NativeMemoryHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
            )

    def test_memory_fingerprint_tamper_is_held(self):
        store = self._store()
        self._remember(store)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET fingerprint=?",
                ("e" * 64,),
            )
        with self.assertRaises(NativeMemoryHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
            )

    def test_memory_namespace_tamper_is_held(self):
        store = self._store()
        self._remember(store)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET namespace_key=?",
                ("other/other/default",),
            )
        with self.assertRaises(NativeMemoryHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
            )

    def test_in_memory_cross_principal_write_is_rejected(self):
        store = self._store()
        bad_scope = MemoryNamespace("foreign", "operator")
        with self.assertRaises(NativeMemoryHold):
            MemoryManager(store=store).remember(
                bad_scope, "cross principal",
                source="forged", trust=0.5,
            )
        self.assertEqual(store.persisted_records, 0)

    def test_run_id_binding_prevents_cross_task_memory_reuse(self):
        store = self._store()
        self._remember(store)
        wrong = self._inputs(text="Another task")
        with self.assertRaises(NativeCheckpointHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), wrong,
            )

    def test_run_id_binding_prevents_cross_run_memory_reuse(self):
        store = self._store()
        self._remember(store)
        other = self._inputs(run_id="different_run")
        with self.assertRaises(NativeCheckpointHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), other,
            )

    def test_cold_foreign_subject_cannot_read_memories(self):
        store = self._store()
        self._remember(store)
        self._cold(subject="foreign")
        with self.assertRaises(NativeCheckpointHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
            )
        self.assertEqual(self.backend.calls, 0)

    def test_same_memory_id_can_update_access_count_but_not_meaning(self):
        store = self._store()
        item = self._remember(store)
        newer = replace(
            item, access_count=2,
            updated_at=item.updated_at + 1,
            last_accessed_at=item.updated_at + 1,
        )
        store.put(newer)
        self.assertEqual(store.persisted_records, 1)
        self.assertEqual(store.get(item.memory_id).access_count, 2)
        forged = replace(item, content="forged other content")
        with self.assertRaises(NativeMemoryHold):
            store.put(forged)
        self.assertEqual(store.persisted_records, 1)

    def test_memory_capacity_is_fail_closed_without_eviction(self):
        store = self._store(capacity=1)
        first = self._remember(store, "first item")
        with self.assertRaises(NativeMemoryHold):
            self._remember(store, "second unique item")
        self.assertEqual(store.persisted_records, 1)
        self.assertEqual(store.get(first.memory_id).content, "first item")

    def test_reopen_with_smaller_limit_rejects_existing_inventory(self):
        store = self._store(capacity=2)
        self._remember(store, "first")
        self._remember(store, "second")
        with self.assertRaises(NativeMemoryHold):
            NativeRunMemoryStore(
                NativeSQLiteCheckpointer(self.worker), self.inputs,
                max_records=1,
            )

    def test_privacy_deletion_cannot_be_fake_in_memory_only(self):
        store = self._store()
        self._remember(store)
        with self.assertRaises(NativeMemoryHold):
            store.delete("fake_memory")
        with self.assertRaises(NativeMemoryHold):
            store.privacy_delete_subject(
                "local", "operator", authority_receipt_digest="f"*64,
            )
        self.assertEqual(store.persisted_records, 1)

    def test_bad_capacity_boolean_rejected(self):
        journal = NativeSQLiteCheckpointer(self.worker)
        journal.create_run(self.inputs)
        for capacity in (0, -1, 257, True, 1.5):
            with self.subTest(capacity=capacity), self.assertRaises(NativeMemoryHold):
                NativeRunMemoryStore(
                    journal, self.inputs, max_records=capacity,
                )

    def test_durable_agent_restores_goal_memory_after_premodel_interrupt(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs)
        self.assertEqual(self.backend.calls, 0)
        self.assertGreaterEqual(
            runner.inspect(self.inputs)["durable_working_memory_records"], 1,
        )
        self._cold()
        restored = NativeDurableJeevesAgent(self.worker)
        result = restored.resume_operator_approved(self.inputs)
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 3)
        self.assertGreaterEqual(
            restored.inspect(self.inputs)["durable_working_memory_records"], 1,
        )

    def test_cold_resume_after_planning_retains_context_and_does_not_replan(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_execute_step",
            side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs)
        self.assertEqual(self.backend.calls, 1)
        self._cold()
        restored = NativeDurableJeevesAgent(self.worker)
        result = restored.resume_operator_approved(self.inputs)
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 2)

    def test_memory_corruption_blocks_planner_resume_preinference(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET payload_sha256=?",
                ("f" * 64,),
            )
        self._cold()
        restored = NativeDurableJeevesAgent(self.worker)
        with self.assertRaises(NativeMemoryHold):
            restored.resume_operator_approved(self.inputs)
        self.assertEqual(self.backend.calls, 0)

    def test_runtime_inspection_fails_closed_on_corrupted_memory(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET payload=?",
                (b'not-json',),
            )
        with self.assertRaises(NativeMemoryHold):
            runner.inspect(self.inputs)

    def test_full_agent_persists_reasoning_memory_and_terminates(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self.inputs)
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 3)
        self.assertTrue(runner.inspect(self.inputs)["terminal_result_saved"])
        self.assertGreaterEqual(
            runner.inspect(self.inputs)["durable_working_memory_records"], 2,
        )
        self._cold()
        recovered = NativeDurableJeevesAgent(self.worker)
        terminal = recovered.replay_terminal(self.inputs)
        self.assertEqual(terminal["answer"], result.answer)
        self.assertEqual(self.backend.calls, 0)


if __name__ == "__main__":
    unittest.main()
