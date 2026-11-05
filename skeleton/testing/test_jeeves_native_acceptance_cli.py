"""Real-turn acceptance orchestration tests with explicitly simulated backend.

Tests exercise proof logic and denial boundaries only. Real installed-model
source, physical laptop, actual native process and cold restart are NOT
qualified by these test doubles.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_acceptance_cli import (
    NativeAcceptanceHold, run_acceptance,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


def arguments(**overrides):
    base = {
        "model_root": Path("/operator/private/model"),
        "state_dir": Path("/operator/private/state"),
        "tenant": "local",
        "subject": "operator",
        "prompt": "Verify one original local model turn.",
        "approved": True,
        "cold_restart": False,
    }
    base.update(overrides)
    return base


def installed(**overrides):
    base = {
        "content_verified": True,
        "rights_approved": True,
        "model_sha256": MODEL,
        "source_sha": "source-test-only",
        "archive_sha256": "archive-test-only",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestRealTurnAcceptanceControls(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.worker.spine.health = lambda: {"simulated": True}
        self.activation = mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.activate_checked",
            return_value=(nullcontext(), self.worker, installed()),
        )
        self.loader = self.activation.start()
        self.addCleanup(self.activation.stop)

    def test_requires_explicit_operator_real_model_approval(self):
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments(approved=False))
        self.loader.assert_not_called()
        self.assertEqual(self.worker.spine.generations, 0)

    def test_declines_empty_user_prompt_before_activation(self):
        with self.assertRaises(ValueError):
            run_acceptance(**arguments(prompt=""))
        self.loader.assert_not_called()

    def test_declines_invalid_tenant_before_activation(self):
        with self.assertRaises(ValueError):
            run_acceptance(**arguments(tenant="foreign space"))
        self.loader.assert_not_called()

    def test_source_rights_receipt_is_mandatory(self):
        self.loader.return_value = (nullcontext(), self.worker, installed(rights_approved=False))
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations, 0)

    def test_source_model_receipt_must_match_native(self):
        self.loader.return_value = (nullcontext(), self.worker, installed(model_sha256="f" * 64))
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations, 0)

    def test_first_turn_uses_existing_native_acceptance(self):
        result = run_acceptance(**arguments())
        self.assertTrue(result["real_native_inference_completed"])
        self.assertTrue(result["sqlite_committed_replay_verified"])
        self.assertEqual(result["model_sha256"], MODEL)
        self.assertEqual(result["tokenizer_sha256"], TOKENIZER)
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertFalse(result["restart_db_inspected"])
        self.assertFalse(result["cold_model_reload_verified"])
        self.assertFalse(result["release_certified"])
        self.assertFalse(result["device_pressure_qualified"])
        self.assertFalse(result["clean_windows_install_qualified"])
        self.assertNotIn("answer", result)
        self.assertNotIn("Verify one original local model turn.", str(result))

    def test_rejected_native_commit_never_claims_evidence(self):
        self.worker.spine.fail_uncertain = True
        with self.assertRaises(RuntimeError):
            run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations, 1)

    def test_cold_model_replay_does_not_generate_again(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={
                "state": "restart-storage-inspected-not-native-resumed",
                "doctor": {"simulation": True},
            },
        ) as doctor:
            result = run_acceptance(**arguments(cold_restart=True))
        self.assertTrue(result["cold_model_reload_verified"])
        self.assertTrue(result["restart_db_inspected"])
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(self.loader.call_count, 2)
        doctor.assert_called_once()

    def test_read_only_doctor_failure_blocks_cold_claim(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state": "not-integrity-checked"},
        ):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments(cold_restart=True))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_cold_replay_mismatch_blocks_claim(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state": "restart-storage-inspected-not-native-resumed"},
        ), mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_replay",
            return_value={
                "committed": True,
                "no_second_generation": True,
                "output_sha256": "f" * 64,
            },
        ):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments(cold_restart=True))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_nonboolean_cold_restart_refused(self):
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments(cold_restart="yes"))
        self.loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
