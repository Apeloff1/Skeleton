"""Real installed GGUF Jeeves acceptance wrapper: synthetic controls only.

Production must pass the typed installed source through require_real=True.
Mocks below test wiring and invalid evidence. They DO NOT certify any
real model weights, source rights, Windows, GPU or consumer release.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stdout, redirect_stderr
from dataclasses import replace
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_acceptance_cli import (
    NativeAcceptanceHold, _publish_summary, main, run_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run as genuine_first_turn,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c"*64, "archive_sha256": "d"*64,
    "source_sha": "e"*40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}
FIRST = {
    "session_id":"s_synthetic", "request_id":"r_synthetic",
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "output_sha256":"f"*64, "generated_tokens":17,
    "installed_source":dict(SOURCE), "native_model_observed":True,
    "installed_source_bound":True, "replayed_without_generation":True,
    "operator_approved_real_inference":True, "release_certified":False,
    "device_qualified":False,
}
COLD = {
    "session_id":"s_synthetic", "request_id":"r_synthetic",
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "output_sha256":"f"*64, "first_turn_generated_tokens":17,
    "source_verified_twice":True,
    "sqlite_replay_after_cold_reopen":True,
    "second_generation_attempted":False, "release_certified":False,
    "physical_device_qualified":False,
}


def arguments(**updates):
    args = {
        "model_root":Path("/private/model"),
        "state_dir":Path("/private/sqlite"),
        "tenant":"local", "subject":"operator",
        "prompt":"  code indent  \r\n",
        "approved":True, "cold_restart":False,
    }
    args.update(updates)
    return args


def installed(**updates):
    values={
        "content_verified":True, "rights_approved":True,
        "release_certified":False, "model_sha256":MODEL,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def cli_args(*extra):
    return [
        "--model-root","/private/model",
        "--state-dir","/private/sqlite",
        "--tenant","local","--subject","operator",
        "--approve-native","--prompt-stdin",*extra,
    ]


class ShortWriter(StringIO):
    def write(self, text):
        super().write(text[:5])
        return 5


class RealAcceptanceWiringTests(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.worker.spine.health=lambda:{"status":"synthetic"}
        self.receipt = installed()
        self.native=mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.activate_checked",
            return_value=(nullcontext(),self.worker,self.receipt),
        )
        self.n=self.native.start()
        self.addCleanup(self.native.stop)
        self.first=mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.run_first_turn",
            return_value=dict(FIRST),
        )
        self.f=self.first.start()
        self.addCleanup(self.first.stop)
        self.witness=mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.require_activated_source",
            return_value=dict(SOURCE),
        )
        self.w=self.witness.start()
        self.addCleanup(self.witness.stop)
        self.cold=mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.run_cold_reopen",
            return_value=dict(COLD),
        )
        self.co=self.cold.start()
        self.addCleanup(self.cold.stop)
        self.doctor=mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.inspect_restart",
            return_value={
                "state":"restart-storage-inspected-not-native-resumed",
            },
        )
        self.d=self.doctor.start()
        self.addCleanup(self.doctor.stop)

    def test_first_turn_delegates_with_typed_installer_receipt_and_real_only(self):
        response=run_acceptance(**arguments())
        self.f.assert_called_once_with(
            self.worker,prompt="  code indent  \r\n",
            approved=True,installed_receipt=self.receipt,require_real=True,
        )
        self.w.assert_called_once_with(self.worker,self.receipt)
        self.assertTrue(response["real_native_inference_completed"])
        self.assertFalse(response["cold_model_reload_verified"])
        self.assertFalse(response["release_certified"])
        self.assertNotIn("code indent",str(response))
        self.assertEqual(self.worker.spine.generations,0)

    def test_unmocked_real_source_witness_refuses_fake_backend(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.run_first_turn",
            side_effect=genuine_first_turn,
        ):
            with self.assertRaises(ContractViolation):
                run_acceptance(**arguments())
        self.assertEqual(self.worker.spine.generations,0)

    def test_missing_approval_refuses_before_gguf(self):
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments(approved=False))
        self.n.assert_not_called()

    def test_fake_rights_receipt_never_starts_generation(self):
        self.receipt=installed(rights_approved=False)
        self.n.return_value=(nullcontext(),self.worker,self.receipt)
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.f.assert_not_called()
        self.assertEqual(self.worker.spine.generations,0)

    def test_foreign_owner_refused_without_sqlite_or_native(self):
        self.worker.spine.identity=replace(
            self.worker.spine.identity,subject="foreign",
        )
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.f.assert_not_called()

    def test_no_positive_receipt_if_native_model_not_observed(self):
        self.f.return_value={**FIRST,"native_model_observed":False}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())
        self.w.assert_not_called()

    def test_no_positive_receipt_if_sqlite_replay_was_not_read_only(self):
        self.f.return_value={**FIRST,"replayed_without_generation":False}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())

    def test_no_positive_receipt_if_model_epoch_is_altered(self):
        self.f.return_value={**FIRST,"model_sha256":"0"*64}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())

    def test_invalid_source_inventory_refuses_positive_first_turn(self):
        for change in (
            {"installed_model_bytes":True},
            {"installed_shard_count":True},
            {"source_sha":"X"*40},
            {"extra":"fake release"},
        ):
            with self.subTest(change=change):
                self.f.return_value={
                    **FIRST,"installed_source":{**SOURCE,**change},
                }
                with self.assertRaises(NativeAcceptanceHold):
                    run_acceptance(**arguments())
        self.w.assert_not_called()

    def test_source_changes_after_health_refuses_positive_proof(self):
        self.w.return_value={**SOURCE,"archive_sha256":"b"*64}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())

    def test_zero_generation_tokens_cannot_be_real_acceptance(self):
        self.f.return_value={**FIRST,"generated_tokens":0}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments())

    def test_cold_path_uses_canonical_reopen_and_doctor_without_new_adapter(self):
        result=run_acceptance(**arguments(cold_restart=True))
        self.co.assert_called_once()
        kw=self.co.call_args.kwargs
        self.assertIs(kw["approved"],True)
        self.assertEqual(kw["prompt"],"  code indent  \r\n")
        self.d.assert_called_once()
        self.n.assert_not_called()
        self.f.assert_not_called()
        self.assertTrue(result["cold_model_reload_verified"])
        self.assertTrue(result["restart_db_inspected"])
        self.assertFalse(result["release_certified"])

    def test_cold_path_denies_second_generation_or_fabricated_source(self):
        for field,value in (
            ("second_generation_attempted",True),
            ("source_verified_twice",False),
            ("sqlite_replay_after_cold_reopen",False),
            ("release_certified",True),
            ("physical_device_qualified",True),
            ("first_turn_generated_tokens",0),
        ):
            with self.subTest(field=field):
                self.co.return_value={**COLD,field:value}
                with self.assertRaises(NativeAcceptanceHold):
                    run_acceptance(**arguments(cold_restart=True))
        self.n.assert_not_called()

    def test_read_only_cold_doctor_is_required_for_positive_report(self):
        self.d.return_value={"state":"not-verified"}
        with self.assertRaises(NativeAcceptanceHold):
            run_acceptance(**arguments(cold_restart=True))

    def test_invalid_prompts_and_roots_are_refused_before_inference(self):
        for field,value in (
            ("prompt",""),("prompt","\x00secret"),
            ("prompt",True),("model_root",Path("relative")),
            ("state_dir",Path("/private/../escape")),
            ("capacity_root",Path("relative")),
            ("tenant","foreign/name"),
            ("approved",1),("cold_restart","yes"),
        ):
            with self.subTest(field=field):
                with self.assertRaises((NativeAcceptanceHold,ValueError)):
                    run_acceptance(**arguments(**{field:value}))
        self.n.assert_not_called()
        self.co.assert_not_called()

    def test_invalid_native_shape_denied_before_activation(self):
        for field,value in (
            ("n_ctx",1),("max_new_tokens",99999),
            ("n_threads",0),("gpu_layers",-1),
            ("capacity_budget_bytes",0),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    run_acceptance(**arguments(**{field:value}))
        self.n.assert_not_called()

    def test_no_device_or_rights_claim_even_on_mocked_positive_cold(self):
        result=run_acceptance(**arguments(cold_restart=True))
        for field in (
            "model_rights_independently_approved_here",
            "device_pressure_qualified","inflight_native_cancellation_qualified",
            "clean_windows_install_qualified","release_certified",
        ):
            self.assertIs(result[field],False)
        self.assertEqual(self.worker.spine.generations,0)


class DigestOnlyNativeOutputTests(unittest.TestCase):
    def setUp(self):
        from skeleton.jeeves.agent.native_acceptance_cli import _public_proof
        self.summary = _public_proof(
            prompt="private",model=MODEL,tokenizer=TOKENIZER,
            digest="f"*64,session="s_one",request="r_one",cold=False,
        )

    def test_bounded_proof_writes_complete_one_jsonl_record(self):
        out=StringIO()
        with redirect_stdout(out):
            _publish_summary(self.summary)
        data=json.loads(out.getvalue())
        self.assertTrue(data["real_native_inference_completed"])
        self.assertFalse(data["release_certified"])
        self.assertNotIn("private",out.getvalue())
        self.assertTrue(out.getvalue().endswith("\n"))

    def test_short_output_write_does_not_claim_success(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_acceptance_cli.sys.stdout",
            ShortWriter(),
        ),self.assertRaises(NativeAcceptanceHold):
            _publish_summary(self.summary)

    def test_extra_private_fields_cannot_enter_public_evidence(self):
        with self.assertRaises(NativeAcceptanceHold):
            _publish_summary({**self.summary,"answer":"PRIVATE MODEL CONTENT"})

    def test_device_claim_or_wrong_digest_is_rejected(self):
        for update in (
            {"release_certified":True},
            {"device_pressure_qualified":True},
            {"restart_db_inspected":True},
            {"model_sha256":"invalid"},
        ):
            with self.subTest(update=update):
                with self.assertRaises((NativeAcceptanceHold,ValueError)):
                    _publish_summary({**self.summary,**update})

    def test_main_preserves_exact_utf8_and_newline_task_content(self):
        from skeleton.jeeves.agent import native_acceptance_cli as module
        raw=b"  def task():\r\n    return 42\r\n"
        stdin=SimpleNamespace(buffer=BytesIO(raw))
        out,err=StringIO(),StringIO()
        with (
            mock.patch.object(module.sys,"stdin",stdin),
            mock.patch.object(module,"run_acceptance",return_value=self.summary) as run,
            redirect_stdout(out),redirect_stderr(err),
        ):
            result=main(cli_args())
        self.assertEqual(result,0,err.getvalue())
        self.assertEqual(run.call_args.kwargs["prompt"],raw.decode("utf8"))
        self.assertEqual(json.loads(out.getvalue())["release_certified"],False)
        self.assertNotIn("def task",out.getvalue())

    def test_invalid_root_and_unapproved_stdin_is_untouched(self):
        from skeleton.jeeves.agent import native_acceptance_cli as module
        for flags in (
            [x for x in cli_args() if x!="--approve-native"],
            cli_args("--model-root","relative"),
            cli_args("--context","0"),
            cli_args("--not-a-real-private-option","PRIVATE"),
        ):
            with self.subTest(flags=flags):
                stdin=SimpleNamespace(buffer=BytesIO(b"private"))
                err=StringIO()
                with (
                    mock.patch.object(module.sys,"stdin",stdin),
                    mock.patch.object(module,"run_acceptance") as run,
                    redirect_stderr(err),
                ):
                    code=main(flags)
                self.assertEqual(code,2)
                self.assertEqual(stdin.buffer.tell(),0)
                self.assertNotIn("PRIVATE",err.getvalue())
                self.assertNotIn("usage:",err.getvalue())
                run.assert_not_called()


if __name__=="__main__":
    unittest.main()
