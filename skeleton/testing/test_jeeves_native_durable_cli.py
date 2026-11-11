"""End-to-end operator CLI plumbing with actual SQLite and a SYNTHETIC model.

Mocking ONLY installation/model readiness avoids a real GGUF forward pass;
all accepted agent planning, durable checkpoint, replay, and CLI parsing run
through their production code paths. These are not physical-device results.
"""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO, StringIO, TextIOWrapper
import json
import os
from pathlib import Path
from types import SimpleNamespace
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
from skeleton.jeeves.agent.native_cli import main as cli_main
from skeleton.jeeves.agent.native_durable_runtime import NativeDurableJeevesAgent
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import Budget, Goal
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ScriptedAgentBackend,
)

# SYNTHETIC source fixture: production still requires verified on-disk
# installer bytes, isolated native child and capacity lease. Patch only the
# source-inspector dependency in these durable-planner/SQLite tests.
SOURCE_ONLY_WITNESS = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 4096,
    "installed_shard_count": 1,
}
SOURCE_WITNESS_UNSPECIFIED = object()


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "protected native SQLite requires Linux /proc")
class TestNativeDurableOperatorCLI(unittest.TestCase):
    TASK = "Reason about the local operator context."
    RUN = "cli_durable_session_001"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jeeves-durable-cli-', dir=Path.home())
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
        self.backend = ScriptedAgentBackend()
        spine = ExecutionSpine(
            db=self.db, session_gate=self.gate, backend=self.backend,
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

    def _argv(self, *extra, subject="operator"):
        return [
            "--model-root", "/not-loaded-model",
            "--state-dir", self.tmp.name,
            "--tenant", "local", "--subject", subject,
            "--mode", "durable-agent",
            "--run-id", self.RUN,
            "--task-stdin", *extra,
        ]

    def _invoke(self, *extra, task=None, subject="operator",
                source_witness=SOURCE_WITNESS_UNSPECIFIED):
        stdin = TextIOWrapper(BytesIO(
            (self.TASK if task is None else task).encode("utf-8"),
        ), encoding="utf-8")
        stdout, stderr = StringIO(), StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_cli.activate_checked",
                return_value=(nullcontext(), self.worker, object()),
            ) as activate,
            mock.patch(
                "skeleton.jeeves.agent.native_cli.inspect_native_jeeves",
                return_value=SimpleNamespace(source_bridge_ready=True),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=(
                    dict(SOURCE_ONLY_WITNESS)
                    if source_witness is SOURCE_WITNESS_UNSPECIFIED
                    else source_witness
                ),
            ),
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            status = cli_main(self._argv(*extra, subject=subject))
        data = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        return status, data, stderr.getvalue(), activate.call_count

    def _inputs(self):
        digest = sha256(self.TASK.encode("utf-8")).hexdigest()
        return RunInputs(
            goal=Goal(
                goal_id="jeeves_native_" + digest[:24],
                objective=self.TASK,
                constraints=(
                    "No unapproved external tools or data writes.",
                    "Mark uncertain claims unresolved.",
                ),
            ),
            tenant_id="local", user_id="operator",
            run_id=self.RUN,
            budget=Budget(
                max_steps=8, max_model_calls=8, max_tool_calls=1,
                max_tokens=16384, max_wall_seconds=180,
            ),
            preferred_provider="jeeves_native",
        )

    def test_forged_installed_source_is_held_before_native_effect(self):
        for source in (
            None, True, {}, {**SOURCE_ONLY_WITNESS, "installed_shard_count": True},
            {**SOURCE_ONLY_WITNESS, "manifest_sha256": "Z" * 64},
            {**SOURCE_ONLY_WITNESS, "tokenizer_sha256": "f" * 64},
            {**SOURCE_ONLY_WITNESS, "unapproved_lease_claim": True},
        ):
            with self.subTest(source=repr(source)):
                code, result, err, activated = self._invoke(
                    source_witness=source,
                )
                self.assertEqual(code, 2)
                self.assertIsNone(result)
                self.assertEqual(activated, 1)
                self.assertEqual(self.backend.calls, 0)
                self.assertNotIn(self.TASK, err)
                self.assertIn('"release_certified": false', err)
        with self.db.snapshot() as conn:
            # A forged installed source must not initialize the Jeeves
            # terminal-result table at all. A pre-existing table is also
            # acceptable, but may not contain a newly committed result.
            present = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='jeeves_native_terminal_results'"
            ).fetchone()[0]
            if present:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM jeeves_native_terminal_results"
                    ).fetchone(), (0,),
                )
            else:
                self.assertEqual(present, 0)

    def test_cli_creates_verified_answer_and_terminal_custody(self):
        code, record, err, activated = self._invoke()
        self.assertEqual(code, 0, err)
        self.assertEqual(activated, 1)
        self.assertEqual(record["status"], "verified-agent-response")
        self.assertTrue(record["success"])
        self.assertEqual(record["answer"], "Local synthetic reasoning completed.")
        self.assertEqual(self.backend.calls, 3)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_terminal_results",
            ).fetchone(), (1,))

    def test_replay_cli_returns_same_exact_answer_without_generation(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        calls = self.backend.calls
        second = self._invoke("--replay-result")
        self.assertEqual(second[0], 0, second[2])
        self.assertTrue(second[1]["replayed"])
        self.assertEqual(second[1]["answer"], first[1]["answer"])
        self.assertEqual(second[1]["reason"], first[1]["termination_reason"])
        self.assertEqual(self.backend.calls, calls)

    def test_inspect_cli_reads_checkpoint_but_not_private_answer(self):
        started = self._invoke()
        self.assertEqual(started[0], 0, started[2])
        code, summary, err, _ = self._invoke("--inspect-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(summary["phase"], "completed")
        self.assertTrue(summary["terminal_result_saved"])
        self.assertFalse(summary["operator_resume_structurally_admissible"])
        self.assertNotIn(self.TASK, json.dumps(summary))
        self.assertNotIn(started[1]["answer"], json.dumps(summary))
        self.assertEqual(self.backend.calls, 3)

    def test_cold_reopen_cli_replays_result_with_no_inference(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        self._cold()
        code, result, err, _ = self._invoke("--replay-result")
        self.assertEqual(code, 0, err)
        self.assertEqual(result["answer"], first[1]["answer"])
        self.assertEqual(self.backend.calls, 0)

    def test_cold_reopen_inspection_preserves_run_identity(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        self._cold()
        code, status, err, _ = self._invoke("--inspect-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(status["run_id"], self.RUN)
        self.assertTrue(status["terminal_result_saved"])
        self.assertEqual(self.backend.calls, 0)

    def test_replay_cannot_swap_private_task_under_same_id(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        self._cold()
        code, data, err, _ = self._invoke(
            "--replay-result", task="Different private user task.",
        )
        self.assertEqual(code, 2)
        self.assertIsNone(data)
        self.assertNotIn("Different private user task.", err)
        self.assertEqual(self.backend.calls, 0)

    def test_foreign_subject_cannot_replay_previous_answer(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        self._cold(subject="other")
        code, data, err, _ = self._invoke(
            "--replay-result", subject="other",
        )
        self.assertEqual(code, 2)
        self.assertIsNone(data)
        self.assertEqual(self.backend.calls, 0)
        self.assertNotIn(self.TASK, err)

    def test_reissued_default_start_never_regenerates_run(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        code, data, err, _ = self._invoke()
        self.assertEqual(code, 2)
        self.assertIsNone(data)
        self.assertEqual(self.backend.calls, 3)
        self.assertIn("NativeCheckpointHold", err)

    def test_completed_run_cannot_be_resumed_by_cli(self):
        first = self._invoke()
        self.assertEqual(first[0], 0, first[2])
        self._cold()
        code, data, err, _ = self._invoke("--resume-run")
        self.assertEqual(code, 2)
        self.assertIsNone(data)
        self.assertEqual(self.backend.calls, 0)

    def test_operator_resume_after_pre_model_interrupt(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self.assertEqual(self.backend.calls, 0)
        self._cold()
        code, result, err, _ = self._invoke("--resume-run")
        self.assertEqual(code, 0, err)
        self.assertTrue(result["success"])
        self.assertEqual(self.backend.calls, 3)

    def test_no_automatic_recovery_of_pre_model_interrupt(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(
            runner.agent.agent, "_plan", side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self._cold()
        code, result, err, _ = self._invoke()
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(self.backend.calls, 0)

    def test_unresolved_model_intent_cannot_resume_cli(self):
        runner = NativeDurableJeevesAgent(self.worker)
        original = runner.checkpoints.save
        def crash_at_model_return(checkpoint):
            if checkpoint.sequence == 3:
                raise KeyboardInterrupt()
            return original(checkpoint)
        with mock.patch.object(
            runner.checkpoints, "save", side_effect=crash_at_model_return,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self.assertEqual(self.backend.calls, 1)
        self._cold()
        code, result, err, _ = self._invoke("--resume-run")
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(self.backend.calls, 0)
        self.assertIn("NativeCheckpointHold", err)

    def test_unresolved_inference_intent_is_visible_in_inspection(self):
        runner = NativeDurableJeevesAgent(self.worker)
        original = runner.checkpoints.save
        with mock.patch.object(
            runner.checkpoints, "save",
            side_effect=lambda checkpoint:
                (_ for _ in ()).throw(KeyboardInterrupt())
                if checkpoint.sequence == 3 else original(checkpoint),
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self._cold()
        code, record, err, _ = self._invoke("--inspect-run")
        self.assertEqual(code, 0, err)
        self.assertTrue(record["unresolved_model_intent"])
        self.assertFalse(record["terminal_result_saved"])
        self.assertFalse(record["operator_resume_structurally_admissible"])
        self.assertEqual(self.backend.calls, 0)

    def test_replay_without_terminal_receipt_is_held(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(runner.agent.agent, "_plan", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self._cold()
        code, result, err, _ = self._invoke("--replay-result")
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(self.backend.calls, 0)

    def test_bad_operator_flags_are_rejected_before_native_activation(self):
        code, result, err, activated = self._invoke(
            "--resume-run", "--inspect-run",
        )
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(activated, 0)
        self.assertIn("NativeOperatorHold", err)

    def test_non_durable_flag_is_rejected_before_native_activation(self):
        code, result, err, activated = self._invoke(
            "--resume-run", "--replay-result",
        )
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertEqual(activated, 0)
        self.assertIn("NativeOperatorHold", err)


if __name__ == "__main__":
    unittest.main()
