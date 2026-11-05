"""Protected read-only cold Jeeves recovery without installing/loading a model.

All SQLite/session/agent state is production code. The deterministic test
generator is SYNTHETIC; these tests are not evidence of physical GGUF, device
cancellation, signed installer rights, or Windows qualification.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
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
from skeleton.jeeves.agent.native_cold_doctor import (
    ColdDoctorHold, inspect_cold_state, main,
)
from skeleton.jeeves.agent.native_durable_runtime import NativeDurableJeevesAgent
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import Budget, Goal
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ScriptedAgentBackend,
)


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "real protected SQLite requires Linux /proc")
class TestNativeReadOnlyColdDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
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
        self.db = SpineDatabase(self.root)
        self.gate = SessionGate(self.root)
        self.backend = ScriptedAgentBackend()
        self.worker = SupervisedAI(ExecutionSpine(
            db=self.db, session_gate=self.gate,
            backend=self.backend,
            identity=Identity("local", "operator", MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        ))

    def _cold(self):
        self._close()
        self._open()

    def _inputs(self, run_id="cold_doctor_001"):
        return RunInputs(
            goal=Goal("doctor_goal_001", "Bounded local reasoning task"),
            tenant_id="local", user_id="operator",
            run_id=run_id, preferred_provider="jeeves_native",
            budget=Budget(
                max_steps=8, max_model_calls=8,
                max_tool_calls=1, max_tokens=16384,
                max_wall_seconds=120,
            ),
        )

    def _inspect(self, *, run_id="cold_doctor_001", **kwargs):
        values = {
            "state_dir": self.root, "tenant": "local",
            "subject": "operator", "model_sha256": MODEL,
            "tokenizer_sha256": TOKENIZER, "run_id": run_id,
        }
        values.update(kwargs)
        return inspect_cold_state(**values)

    def _run(self):
        runner = NativeDurableJeevesAgent(self.worker)
        result = runner.run(self._inputs())
        self.assertTrue(result.success)
        return runner, result

    def test_successful_run_cold_doctor_without_model_load(self):
        _, result = self._run()
        self._cold()
        report = self._inspect()
        self.assertEqual(report["status"], "inspected-readonly-not-resumed")
        self.assertEqual(report["checkpoint_phase"], "completed")
        self.assertTrue(report["terminal_answer_sealed"])
        self.assertFalse(report["unresolved_inference_intent"])
        self.assertFalse(report["operator_resume_structurally_admissible"])
        self.assertFalse(report["native_model_called"])
        self.assertEqual(self.backend.calls, 0)

    def test_real_sqlite_read_only_doctor_does_not_change_custody(self):
        runner, result = self._run()
        with self.db.snapshot() as conn:
            before = conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_checkpoints",
            ).fetchone()[0]
        self._inspect()
        with self.db.snapshot() as conn:
            after = conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_checkpoints",
            ).fetchone()[0]
        self.assertEqual(before, after)

    def test_unresolved_native_intent_is_reported_but_never_retried(self):
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
        self.assertEqual(self.backend.calls, 1)
        self._cold()
        report = self._inspect()
        self.assertTrue(report["unresolved_inference_intent"])
        self.assertFalse(report["operator_resume_structurally_admissible"])
        self.assertEqual(self.backend.calls, 0)

    def test_pre_model_abort_is_candidate_not_automatic_resumption(self):
        runner = NativeDurableJeevesAgent(self.worker)
        with mock.patch.object(runner.agent.agent, "_plan", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        self._cold()
        report = self._inspect()
        self.assertEqual(report["checkpoint_phase"], "planning")
        self.assertTrue(report["operator_resume_structurally_admissible"])
        self.assertFalse(report["native_model_loaded"])
        self.assertEqual(self.backend.calls, 0)

    def test_missing_model_activation_is_not_reported_as_success(self):
        self._run()
        report = self._inspect()
        self.assertFalse(report["native_model_loaded"])
        self.assertFalse(report["native_model_called"])
        self.assertFalse(report["release_certified"])

    def test_all_working_memory_counts_are_scoped_and_no_text_disclosed(self):
        self._run()
        report = self._inspect()
        self.assertGreater(report["run_scoped_memory_count"], 0)
        self.assertNotIn("Bounded local reasoning task", str(report))
        self.assertNotIn("Local synthetic reasoning completed", str(report))

    def test_foreign_subject_is_held_before_reading_private_memory(self):
        self._run()
        with self.assertRaises(ColdDoctorHold):
            self._inspect(subject="different")
        self.assertEqual(self.backend.calls, 3)

    def test_wrong_model_digest_is_held(self):
        self._run()
        with self.assertRaises(ColdDoctorHold):
            self._inspect(model_sha256="f" * 64)

    def test_wrong_tokenizer_digest_is_held(self):
        self._run()
        with self.assertRaises(ColdDoctorHold):
            self._inspect(tokenizer_sha256="f" * 64)

    def test_missing_run_does_not_leak_foreign_state(self):
        self._run()
        with self.assertRaises(ColdDoctorHold):
            self._inspect(run_id="nonexistent")

    def test_checkpoint_payload_tamper_is_detected(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_checkpoints SET payload=?",
                (b'{"tampered":true}',),
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_checkpoint_chain_tip_tamper_is_detected(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_runs SET tip_hash=?",
                ("f" * 64,),
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_missing_checkpoint_row_is_detected(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM jeeves_native_checkpoints "
                "WHERE sequence=(SELECT MAX(sequence) FROM jeeves_native_checkpoints)",
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_terminal_answer_tamper_is_detected_without_disclosure(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_terminal_results SET payload=?",
                (b'{"answer":"forged"}',),
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_terminal_checksum_tamper_is_detected(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_terminal_results SET payload_sha256=?",
                ("f" * 64,),
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_memory_bitflip_is_detected_without_cold_model(self):
        self._run()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_memories SET payload=?",
                (b'{"sensitive":"forged"}',),
            )
        with self.assertRaises(ColdDoctorHold):
            self._inspect()

    def test_read_only_conn_will_not_create_missing_database(self):
        other = self.root / "missing-dir"
        other.mkdir(mode=0o700)
        with self.assertRaises(Exception):
            self._inspect(state_dir=other)
        self.assertFalse((other / "ai-spine.sqlite").exists())

    def test_relative_root_is_rejected_before_any_sqlite_read(self):
        with self.assertRaises(ColdDoctorHold):
            self._inspect(state_dir=Path("relative"))

    def test_path_with_dotdot_is_rejected_before_any_database_read(self):
        with self.assertRaises(ColdDoctorHold):
            self._inspect(state_dir=self.root / ".." / "relative")

    def test_noncanonical_run_id_is_rejected(self):
        self._run()
        for run_id in ("../../other", "", "injection\0", "space within"):
            with self.subTest(run_id=run_id), self.assertRaises(Exception):
                self._inspect(run_id=run_id)

    def test_cli_emits_only_status_record_and_no_private_answer(self):
        self._run()
        import json
        from contextlib import redirect_stdout, redirect_stderr
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "--state-dir", str(self.root), "--tenant", "local",
                "--subject", "operator", "--model-sha256", MODEL,
                "--tokenizer-sha256", TOKENIZER, "--run-id", "cold_doctor_001",
            ])
        self.assertEqual(code, 0, stderr.getvalue())
        record = json.loads(stdout.getvalue())
        self.assertTrue(record["terminal_answer_sealed"])
        self.assertNotIn("Local synthetic reasoning completed", stdout.getvalue())

    def test_cli_failure_redacts_source_path_and_other_principal(self):
        self._run()
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "--state-dir", str(self.root), "--tenant", "other",
                "--subject", "operator", "--model-sha256", MODEL,
                "--tokenizer-sha256", TOKENIZER, "--run-id", "cold_doctor_001",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(str(self.root), stderr.getvalue())
        self.assertIn('"status": "held"', stderr.getvalue())

    def test_pending_native_request_counts_are_principal_scoped(self):
        runner = NativeDurableJeevesAgent(self.worker)
        original = runner.checkpoints.save
        with mock.patch.object(
            runner.checkpoints, "save",
            side_effect=lambda x: (_ for _ in ()).throw(KeyboardInterrupt())
            if x.sequence == 3 else original(x),
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._inputs())
        report = self._inspect()
        self.assertEqual(report["principal_request_counts"]["committed"], 1)
        self.assertEqual(report["principal_request_counts"]["pending"], 0)
        self.assertTrue(report["unresolved_inference_intent"])

    def test_no_native_loader_is_invoked_by_read_only_doctor(self):
        self._run()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.startup.activate_checked",
            side_effect=AssertionError("GGUF must not be loaded"),
        ) as forbidden:
            report = self._inspect()
        forbidden.assert_not_called()
        self.assertFalse(report["native_model_loaded"])


if __name__ == "__main__":
    unittest.main()
