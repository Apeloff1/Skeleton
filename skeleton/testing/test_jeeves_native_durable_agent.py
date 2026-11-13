"""Cold Jeeves planner recovery using actual SQLite and synthetic GGUF-shaped output.

No device, model license or true native inference claims are made here.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
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
from skeleton.jeeves.agent.native_durable_runtime import (
    NativeDurableAgentHold, NativeDurableJeevesAgent,
)
from skeleton.jeeves.agent.native_checkpoint_journal import NativeCheckpointHold
from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold, check_operator_admission,
)
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import Budget, Goal
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ScriptedAgentBackend,
)


def admission(**overrides):
    values = dict(
        mode="durable-agent", task_stdin=True,
        session=None, request_id=None,
        source_root=None, signed_source_manifest=None,
        enable_source_tool=False, max_sources=4,
        max_steps=8, max_model_calls=8, max_wall_seconds=120,
        run_id="durable_approved", resume_run=False, inspect_run=False,
        replay_result=False,
    )
    values.update(overrides)
    return check_operator_admission(**values)


class TestDurableOperatorAdmission(unittest.TestCase):
    def test_explicit_reasoning_only_durable_run(self):
        approved = admission()
        self.assertEqual(approved.run_id, "durable_approved")
        self.assertTrue(approved.public_receipt()["durable_checkpoint_lane"])

    def test_resume_is_explicit_and_not_automatic(self):
        approved = admission(resume_run=True)
        self.assertTrue(approved.resume_run)
        self.assertTrue(approved.public_receipt()["operator_resume_requested"])

    def test_inspection_is_distinct_from_resume(self):
        approved = admission(inspect_run=True)
        self.assertTrue(approved.inspect_run)
        with self.assertRaises(NativeOperatorHold):
            admission(inspect_run=True, resume_run=True)

    def test_terminal_replay_operator_option_is_explicit(self):
        approved = admission(replay_result=True)
        self.assertTrue(approved.replay_result)
        self.assertTrue(approved.public_receipt()["terminal_replay_requested"])

    def test_inspect_resume_and_replay_are_mutually_exclusive(self):
        for flags in (
            dict(resume_run=True, replay_result=True),
            dict(inspect_run=True, replay_result=True),
            dict(resume_run=True, inspect_run=True, replay_result=True),
        ):
            with self.subTest(flags=flags), self.assertRaises(NativeOperatorHold):
                admission(**flags)

    def test_replay_option_must_be_exact_boolean(self):
        for value in ("on", 1, None):
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                admission(replay_result=value)

    def test_non_durable_modes_cannot_obtain_terminal_replay(self):
        for mode in ("chat", "agent", "repl"):
            with self.subTest(mode=mode), self.assertRaises(NativeOperatorHold):
                admission(mode=mode, run_id=None, replay_result=True)

    def test_run_id_required_and_typed(self):
        for value in (None, "", "has whitespace", False, "foo/../bar"):
            with self.subTest(value=value), self.assertRaises(Exception):
                admission(run_id=value)

    def test_source_grants_and_source_paths_are_not_replayed(self):
        with self.assertRaises(NativeOperatorHold):
            admission(enable_source_tool=True)
        with self.assertRaises(NativeOperatorHold):
            admission(source_root=Path("/private/sources"))
        with self.assertRaises(NativeOperatorHold):
            admission(signed_source_manifest=Path("/private/manifest"))

    def test_durable_flag_cannot_be_sneaked_into_other_modes(self):
        for mode in ("agent", "chat", "repl"):
            with self.subTest(mode=mode), self.assertRaises(NativeOperatorHold):
                admission(mode=mode, run_id=None, resume_run=True)
            with self.subTest(mode=mode), self.assertRaises(NativeOperatorHold):
                admission(mode=mode, run_id="borrowed")

    def test_foreign_chat_ids_rejected_in_durable_mode(self):
        with self.assertRaises(NativeOperatorHold):
            admission(session="s_older")
        with self.assertRaises(NativeOperatorHold):
            admission(request_id="r_older")

    def test_durable_boolean_flags_must_be_exact_bool(self):
        for value in (1, "yes", None):
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                admission(resume_run=value)
            with self.subTest(value=value), self.assertRaises(NativeOperatorHold):
                admission(inspect_run=value)


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "protected native SQLite requires Linux /proc")
class TestDurableAgentWithRealSqlite(unittest.TestCase):
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

    def _open(self):
        self.db = SpineDatabase(self.tmp.name)
        self.gate = SessionGate(self.tmp.name)
        self.backend = ScriptedAgentBackend()
        spine = ExecutionSpine(
            db=self.db, session_gate=self.gate, backend=self.backend,
            identity=Identity("local", "operator", MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        )
        self.worker = SupervisedAI(spine)

    def _cold(self):
        self._close()
        self._open()

    def inputs(self, *, text="Local reasoning task", run_id="durable_run_1"):
        return RunInputs(
            goal=Goal("durable_goal_1", text),
            tenant_id="local", user_id="operator",
            run_id=run_id, preferred_provider="jeeves_native",
            budget=Budget(
                max_steps=8, max_model_calls=8, max_tool_calls=1,
                max_tokens=16000, max_wall_seconds=120,
            ),
        )

    def test_full_agent_writes_native_receipts_and_durable_planner_checkpoint(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self.inputs())
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 3)
        self.assertEqual(result.usage.model_calls, 3)
        receipt = runner.inspect(self.inputs())
        self.assertEqual(receipt["phase"], "completed")
        self.assertGreater(receipt["checkpoint_sequence"], 3)
        self.assertFalse(receipt["unresolved_model_intent"])
        self.assertFalse(receipt["operator_resume_structurally_admissible"])
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (3,),
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM jeeves_native_inflight").fetchone(), (0,),
            )
            self.assertGreater(
                conn.execute("SELECT COUNT(*) FROM jeeves_native_checkpoints").fetchone()[0],
                3,
            )

    def test_terminal_answer_can_be_replayed_without_any_new_generation(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self.inputs())
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 3)
        sealed = runner.replay_terminal(self.inputs())
        self.assertTrue(sealed["replayed"])
        self.assertEqual(sealed["answer"], result.answer)
        self.assertEqual(sealed["trace_fingerprint"], result.trace_fingerprint)
        self.assertEqual(sealed["reason"], result.reason.value)
        self.assertEqual(self.backend.calls, 3)
        self.assertTrue(runner.inspect(self.inputs())["terminal_result_saved"])

    def test_cold_reopen_replays_sealed_answer_without_model_call(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self.inputs())
        self._cold()
        fresh = NativeDurableJeevesAgent(self.worker)
        replay = fresh.replay_terminal(self.inputs())
        self.assertEqual(replay["answer"], result.answer)
        self.assertEqual(replay["trace_fingerprint"], result.trace_fingerprint)
        self.assertEqual(self.backend.calls, 0)

    def test_terminal_answer_bytes_corruption_fails_closed(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_terminal_results SET payload=?",
                (b'{"answer":"forged"}',),
            )
        with self.assertRaises(NativeCheckpointHold):
            runner.replay_terminal(self.inputs())
        self.assertEqual(self.backend.calls, 3)

    def test_terminal_receipt_checksum_corruption_is_held(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_terminal_results SET payload_sha256=?",
                ("f" * 64,),
            )
        with self.assertRaises(NativeCheckpointHold):
            runner.replay_terminal(self.inputs())

    def test_terminal_result_cannot_be_overwritten(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self.inputs())
        with self.assertRaises(NativeCheckpointHold):
            runner.checkpoints.write_terminal_result(result)
        self.assertEqual(runner.replay_terminal(self.inputs())["answer"], result.answer)

    def test_checkpoint_tip_change_refuses_terminal_replay(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_terminal_results SET checkpoint_tip_hash=?",
                ("f" * 64,),
            )
        with self.assertRaises(NativeCheckpointHold):
            runner.replay_terminal(self.inputs())

    def test_missing_receipt_does_not_authorize_terminal_regeneration(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM jeeves_native_terminal_results")
        self._cold()
        recovered = NativeDurableJeevesAgent(self.worker)
        self.assertFalse(recovered.inspect(self.inputs())["terminal_result_saved"])
        with self.assertRaises(NativeDurableAgentHold):
            recovered.replay_terminal(self.inputs())
        with self.assertRaises(NativeDurableAgentHold):
            recovered.resume_operator_approved(self.inputs())
        self.assertEqual(self.backend.calls, 0)

    def test_completed_receipt_replay_requires_exact_input_binding(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        self._cold()
        fresh = NativeDurableJeevesAgent(self.worker)
        with self.assertRaises(NativeCheckpointHold):
            fresh.replay_terminal(self.inputs(text="forged task"))
        self.assertEqual(self.backend.calls, 0)

    def test_before_terminal_checkpoint_replay_fails_closed(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(runner.agent.agent, "_plan", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs())
        with self.assertRaises(NativeDurableAgentHold):
            runner.replay_terminal(self.inputs())
        self.assertFalse(runner.inspect(self.inputs())["terminal_result_saved"])

    def test_successful_run_cannot_be_reissued_with_same_id(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        with self.assertRaises(NativeCheckpointHold):
            runner.run(self.inputs())
        self.assertEqual(self.backend.calls, 3)

    def test_completed_run_cannot_resume_and_regenerate(self):
        runner = NativeDurableJeevesAgent(self.worker)
        runner.run(self.inputs())
        self._cold()
        resumed = NativeDurableJeevesAgent(self.worker)
        with self.assertRaises(NativeDurableAgentHold):
            resumed.resume_operator_approved(self.inputs())
        self.assertEqual(self.backend.calls, 0)

    def test_pre_model_interrupt_recovers_from_durable_created_or_planning_phase(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs())
        self.assertEqual(self.backend.calls, 0)
        record = runner.inspect(self.inputs())
        self.assertEqual(record["phase"], "planning")
        self.assertTrue(record["operator_resume_structurally_admissible"])
        self._cold()
        resumed = NativeDurableJeevesAgent(self.worker)
        result = resumed.resume_operator_approved(self.inputs())
        self.assertTrue(result.success)
        self.assertEqual(self.backend.calls, 3)
        self.assertEqual(resumed.inspect(self.inputs())["phase"], "completed")

    def test_crash_after_committed_inference_before_checkpoint_is_held(self):
        runner = NativeDurableJeevesAgent(self.worker)
        original = runner.checkpoints.save
        def crash_at_model_return(checkpoint):
            if checkpoint.sequence == 3:
                # Only the journal write is interrupted. The native SQLite
                # inference has already committed and MUST NOT be redone.
                raise KeyboardInterrupt()
            return original(checkpoint)
        with mock.patch.object(
            runner.checkpoints, "save", side_effect=crash_at_model_return,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs())
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (1,))
        self._cold()
        recovered = NativeDurableJeevesAgent(self.worker)
        observed = recovered.inspect(self.inputs())
        self.assertTrue(observed["unresolved_model_intent"])
        self.assertFalse(observed["operator_resume_structurally_admissible"])
        with self.assertRaises(NativeCheckpointHold):
            recovered.resume_operator_approved(self.inputs())
        self.assertEqual(self.backend.calls, 0)

    def test_changed_prompt_or_budgets_denied_without_native_generation(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(runner.agent.agent, "_plan", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs())
        self._cold()
        recovered = NativeDurableJeevesAgent(self.worker)
        with self.assertRaises(NativeCheckpointHold):
            recovered.resume_operator_approved(self.inputs(text="different task"))
        self.assertEqual(self.backend.calls, 0)

    def test_no_auto_resumption_when_operator_only_inspects(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(runner.agent.agent, "_plan", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self.inputs())
        self._cold()
        inspector = NativeDurableJeevesAgent(self.worker)
        status = inspector.inspect(self.inputs())
        self.assertTrue(status["operator_resume_structurally_admissible"])
        self.assertEqual(self.backend.calls, 0)

    def test_no_forged_foreign_principal_admission(self):
        runner = NativeDurableJeevesAgent(self.worker)
        foreign = RunInputs(
            goal=Goal("goal_foreign", "No"),
            tenant_id="other", user_id="operator",
            run_id="foreign_run", preferred_provider="jeeves_native",
        )
        with self.assertRaises(NativeDurableAgentHold):
            runner.run(foreign)
        self.assertEqual(self.backend.calls, 0)

    def test_explicit_run_id_is_mandatory(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with self.assertRaises(NativeDurableAgentHold):
            runner.run(RunInputs(
                goal=Goal("missing_id", "Task"),
                tenant_id="local", user_id="operator",
                preferred_provider="jeeves_native",
            ))
        self.assertEqual(self.backend.calls, 0)


if __name__ == "__main__":
    unittest.main()
