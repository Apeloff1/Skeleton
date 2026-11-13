"""First-laptop installed source and cold SQLite acceptance orchestration.

Every source report and inference in this suite is explicitly simulated.
Source-only success can never certify actual GGUF weights, operator rights,
native hardware, Windows/WSL2, cancellation or release readiness.
"""
from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run as simulated_first_turn,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.jeeves.agent.native_acceptance_cli import (
    NativeAcceptanceHold, main, run_acceptance,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


SOURCE = {
    "model_sha256": MODEL,
    "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64,
    "archive_sha256": "d" * 64,
    "source_sha": "e" * 40,
    "installed_model_bytes": 4096,
    "installed_shard_count": 1,
}


def arguments(**overrides):
    values = {
        "model_root": Path("/operator/private/model"),
        "state_dir": Path("/operator/private/state"),
        "tenant": "local",
        "subject": "operator",
        "prompt": "  Verify one original local model turn. \n",
        "approved": True,
        "cold_restart": False,
    }
    values.update(overrides)
    return values


def installed(**overrides):
    data = {
        "model_sha256": MODEL,
        "content_verified": True,
        "rights_approved": True,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class SyntheticFence:
    """Only a test double; real NativeSourceFence requires isolated GGUF."""

    def __init__(self, worker):
        self.worker = worker
        self.owner = ActiveModel.from_supervisor(worker)
        self.calls = 0

    def assert_live(self, worker):
        self.calls += 1
        if worker is not self.worker:
            raise NativeAcceptanceHold("synthetic worker replaced")
        if ActiveModel.from_supervisor(worker) != self.owner:
            raise NativeAcceptanceHold("synthetic principal replaced")


class AcceptanceOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.worker.spine.health = lambda: {"simulated": True}
        self.cold_worker = SimulatedWorker()
        self.cold_worker.spine.health = lambda: {"simulated": True}
        self.receipt = installed()
        self.source = dict(SOURCE)
        self.inference_calls = []
        self.fences = []
        self.latest_digest = None

        self.native = mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.activate_checked",
            return_value=(ExitStack(), self.worker, self.receipt),
        ).start()
        self.addCleanup(mock.patch.stopall)

        self.witness = mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.require_activated_source",
            side_effect=lambda worker, receipt: dict(self.source),
        ).start()

        def guard(worker, receipt, *, expected_tenant, expected_subject):
            self.assertEqual(expected_tenant, "local")
            self.assertEqual(expected_subject, "operator")
            fence = SyntheticFence(worker)
            self.fences.append(fence)
            return fence

        self.fence_factory = mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.NativeSourceFence",
            side_effect=guard,
        ).start()

        def first(worker, *, prompt, approved, installed_receipt, require_real):
            self.assertIs(installed_receipt, self.receipt)
            self.assertIs(approved, True)
            self.assertIs(require_real, True)
            self.inference_calls.append(prompt)
            result = simulated_first_turn(
                worker, prompt=prompt, approved=True,
            )
            self.latest_digest = result["output_sha256"]
            result.update({
                "native_model_observed": True,
                "installed_source_bound": True,
                "operator_approved_real_inference": True,
                "installed_source": dict(self.source),
            })
            return result

        self.first = mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.run_first_turn",
            side_effect=first,
        ).start()

    def cold(self):
        self.native.side_effect = [
            (ExitStack(), self.worker, self.receipt),
            (ExitStack(), self.cold_worker, self.receipt),
        ]

    def test_missing_approval_denies_before_source_or_native(self):
        for approval in (False, 1, None):
            with self.subTest(approval=approval):
                with self.assertRaises(NativeAcceptanceHold):
                    run_acceptance(**arguments(approved=approval))
        self.native.assert_not_called()
        self.witness.assert_not_called()

    def test_invalid_prompt_and_paths_denied_before_activation(self):
        for change in (
            {"prompt": ""},
            {"prompt": "\x00secret"},
            {"model_root": Path("relative/model")},
            {"state_dir": Path("/private/../state")},
            {"capacity_root": Path("relative/leases")},
            {"tenant": "bad scope"},
            {"subject": "foreign/owner"},
            {"n_ctx": 8},
            {"max_new_tokens": 90000},
            {"n_threads": 0},
        ):
            with self.subTest(change=repr(change)):
                with self.assertRaises(ValueError):
                    run_acceptance(**arguments(**change))
        self.native.assert_not_called()
        self.witness.assert_not_called()

    def test_source_report_requires_exact_approval_boolean_and_model(self):
        for change in (
            {"content_verified": 1},
            {"content_verified": False},
            {"rights_approved": 1},
            {"rights_approved": False},
            {"model_sha256": "f" * 64},
        ):
            with self.subTest(change=change):
                self.native.return_value = (
                    ExitStack(), self.worker, installed(**change),
                )
                with self.assertRaises(NativeAcceptanceHold):
                    run_acceptance(**arguments())
        self.first.assert_not_called()
        self.assertEqual(self.worker.spine.generations, 0)

    def test_invalid_source_inventory_denied_before_sqlite(self):
        for changes in (
            {"installed_model_bytes": True},
            {"installed_shard_count": False},
            {"manifest_sha256": "A" * 64},
            {"archive_sha256": "Z" * 64},
            {"source_sha": "g" * 40},
            {"extra": True},
        ):
            with self.subTest(change=changes):
                self.source = {**SOURCE, **changes}
                with self.assertRaises(NativeAcceptanceHold):
                    run_acceptance(**arguments())
        self.first.assert_not_called()
        self.assertEqual(self.worker.spine.generations, 0)

    def test_actual_first_turn_receives_required_real_installed_receipt(self):
        report = run_acceptance(**arguments())
        self.assertEqual(self.inference_calls, [arguments()["prompt"]])
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(report["model_sha256"], MODEL)
        self.assertEqual(report["tokenizer_sha256"], TOKENIZER)
        self.assertEqual(report["output_sha256"], self.latest_digest)
        self.assertTrue(report["real_native_inference_completed"])
        self.assertTrue(report["sqlite_committed_replay_verified"])
        self.assertFalse(report["cold_model_reload_verified"])
        self.assertFalse(report["release_certified"])
        self.assertFalse(report["device_pressure_qualified"])
        self.assertNotIn(arguments()["prompt"], str(report))
        self.assertEqual(len(self.fences), 1)
        self.assertGreaterEqual(self.fences[0].calls, 3)

    def test_unverified_first_turn_cannot_be_relabelled_real(self):
        self.first.side_effect = simulated_first_turn
        with self.assertRaises(ContractViolation):
            run_acceptance(**arguments())
        # Actual lower-level code received the fake receipt and refused
        # the simulated worker, instead of returning a false success.
        self.assertEqual(self.worker.spine.generations, 0)

    def test_uncertain_native_effect_never_retried(self):
        self.worker.spine.fail_uncertain = True
        with self.assertRaises(RuntimeError):
            run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(len(self.inference_calls), 1)

    def test_source_principal_change_cannot_publish_receipt(self):
        from dataclasses import replace
        swapped = replace(self.worker.spine.identity, subject="foreign")
        with mock.patch.object(self.worker.spine, "identity", swapped):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments())
        self.first.assert_not_called()

    def test_real_source_evidence_must_be_preserved_through_first_turn(self):
        def fabricated(*args, **kwargs):
            return {
                "native_model_observed": True,
                "installed_source_bound": False,
            }
        self.first.side_effect = fabricated
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations, 0)

    def test_publisher_runs_inside_live_source_activation(self):
        events = []
        def publish(worker, fence, result):
            fence.assert_live(worker)
            self.assertEqual(result["status"], "native-first-turn-committed-and-replayed")
            self.assertEqual(worker.spine.generations, 1)
            events.append("published-while-live")
        proof = run_acceptance(**arguments(publisher=publish))
        self.assertEqual(events, ["published-while-live"])
        self.assertFalse(proof["release_certified"])

    def test_cold_restart_requires_second_independent_worker(self):
        self.cold()
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state":"restart-storage-inspected-not-native-resumed"},
        ) as doctor, mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_replay",
            side_effect=lambda *a, **k: {
                "committed": True, "no_second_generation": True,
                "output_sha256": self.latest_digest,
            },
        ) as replay:
            result = run_acceptance(**arguments(cold_restart=True))
        doctor.assert_called_once()
        replay.assert_called_once()
        self.assertTrue(result["restart_db_inspected"])
        self.assertTrue(result["cold_model_reload_verified"])
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(self.cold_worker.spine.generations, 0)
        self.assertEqual(self.native.call_count, 2)
        self.assertEqual(len(self.fences), 2)

    def test_reused_first_worker_cannot_be_called_cold_restart(self):
        self.native.side_effect = [
            (ExitStack(), self.worker, self.receipt),
            (ExitStack(), self.worker, self.receipt),
        ]
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state":"restart-storage-inspected-not-native-resumed"},
        ):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments(cold_restart=True))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_rejected_restart_doctor_prevents_second_activation(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state":"not-inspected"},
        ):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments(cold_restart=True))
        self.assertEqual(self.native.call_count, 1)

    def test_cold_replay_digest_mismatch_blocks_success(self):
        self.cold()
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={"state":"restart-storage-inspected-not-native-resumed"},
        ), mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_replay",
            return_value={
                "committed": True, "no_second_generation": True,
                "output_sha256": "f" * 64,
            },
        ):
            with self.assertRaises(NativeAcceptanceHold):
                run_acceptance(**arguments(cold_restart=True))
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(self.cold_worker.spine.generations, 0)

    def test_nonboolean_cold_request_does_not_activate_model(self):
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments(cold_restart="yes"))
        self.native.assert_not_called()

    def test_cli_publishes_approved_digest_only_while_source_is_live(self):
        stdin = SimpleNamespace(buffer=BytesIO(arguments()["prompt"].encode()))
        out, err = StringIO(), StringIO()
        with (
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stdin", stdin),
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stdout", out),
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stderr", err),
        ):
            code = main([
                "--model-root", "/operator/private/model",
                "--state-dir", "/operator/private/state",
                "--tenant", "local", "--subject", "operator",
                "--approve-native", "--prompt-stdin",
            ])
        self.assertEqual(code, 0, err.getvalue())
        report = json.loads(out.getvalue())
        self.assertEqual(report["output_sha256"], self.latest_digest)
        self.assertTrue(report["real_native_inference_completed"])
        self.assertFalse(report["release_certified"])
        self.assertNotIn(arguments()["prompt"], out.getvalue())
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertFalse(err.getvalue())


class AcceptanceOperatorCLIAdmission(unittest.TestCase):
    def run_cli(self, *extra, raw=b"  exact private native prompt \r\n"):
        argv = [
            "--model-root","/operator/private/model",
            "--state-dir","/operator/private/state",
            "--tenant","local","--subject","operator",
            "--approve-native","--prompt-stdin", *extra,
        ]
        stdin = SimpleNamespace(buffer=BytesIO(raw))
        out, err = StringIO(), StringIO()
        with (
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stdin", stdin),
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stdout", out),
            mock.patch("skeleton.jeeves.agent.native_acceptance_cli.sys.stderr", err),
            mock.patch(
                "skeleton.jeeves.agent.native_acceptance_cli.run_acceptance",
                return_value={"status":"synthetic-only"},
            ) as accepted,
        ):
            status = main(argv)
        return status, out.getvalue(), err.getvalue(), stdin, accepted

    def test_cli_preserves_exact_private_whitespace_for_real_verifier(self):
        status, out, err, inp, accepted = self.run_cli()
        self.assertEqual(status, 0, err)
        self.assertFalse(out)
        accepted.assert_called_once()
        self.assertEqual(
            accepted.call_args.kwargs["prompt"],
            "  exact private native prompt \r\n",
        )
        self.assertTrue(callable(accepted.call_args.kwargs["publisher"]))

    def test_invalid_native_shape_before_private_stdin(self):
        for flag,value in (
            ("--context","1"),
            ("--max-new-tokens","999999"),
            ("--threads","0"),
            ("--gpu-layers","-1"),
            ("--capacity-budget-bytes","0"),
        ):
            with self.subTest(flag=flag):
                status,out,err,inp,accepted = self.run_cli(flag,value)
                self.assertEqual(status,2)
                self.assertEqual(inp.buffer.tell(),0)
                accepted.assert_not_called()
                self.assertEqual(out,"")

    def test_invalid_private_paths_before_stdin(self):
        for flag,value in (
            ("--model-root","relative.gguf"),
            ("--state-dir","/private/../escaped"),
            ("--capacity-root","../secret"),
        ):
            with self.subTest(flag=flag):
                status,out,err,inp,accepted = self.run_cli(flag,value)
                self.assertEqual(status,2)
                self.assertEqual(inp.buffer.tell(),0)
                self.assertNotIn(value,err)
                accepted.assert_not_called()

    def test_unknown_private_flag_is_redacted_without_stdin_read(self):
        secret = "SECRET_DO_NOT_LOG"
        status,out,err,inp,accepted = self.run_cli(
            "--unexpected",secret,
        )
        self.assertEqual(status,2)
        self.assertFalse(out)
        self.assertNotIn(secret,err)
        self.assertNotIn("usage:",err)
        self.assertEqual(inp.buffer.tell(),0)
        accepted.assert_not_called()

    def test_invalid_utf8_cannot_start_native(self):
        status,out,err,inp,accepted = self.run_cli(raw=b"\xff")
        self.assertEqual(status,2)
        self.assertFalse(out)
        accepted.assert_not_called()

    def test_oversize_stdin_cannot_start_native(self):
        status,out,err,inp,accepted = self.run_cli(raw=b"a"*32769)
        self.assertEqual(status,2)
        self.assertFalse(out)
        accepted.assert_not_called()


if __name__ == "__main__":
    unittest.main()
