"""RAM-only desktop owner gate qualification for real GGUF campaign workflows.

Every test uses strict original native request identities; only effects are
mocked. These source tests cannot certify physical model inference.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_campaign_operator as operator,
    desktop_campaign_ui as ui,
    desktop_app,
    desktop_native_campaign as campaign,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli import (
    execute_native_request, SCHEMA as NATIVE_SCHEMA,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace import _canonical


A = "a" * 64
B = "b" * 64
C = "c" * 64


def original_request() -> dict:
    native = {
        "schema": NATIVE_SCHEMA,
        "action": "inspect",
        "project_root": "/owner/project",
        "model_root": "/owner/model",
        "state_dir": "/owner/state",
        "tenant": "owner", "subject": "local",
        "goal": "Generate a bounded original Python module",
        "format": "new-files", "maximum_attempts": 1,
        "source_paths": [], "source_context_sha256": None,
        "job_sha256": None,
        "context_tokens": 1024, "max_output_tokens": 128,
        "threads": 2, "gpu_layers": 0, "inference_ms": 1000,
        "capacity_budget_bytes": 2**30,
    }
    digest = execute_native_request(native)["job_sha256"]
    native["action"], native["job_sha256"] = "generate", digest
    return {
        "schema": campaign.SCHEMA,
        "action": "inspect",
        "project_root": "/owner/project",
        "journal_file": "/owner/private/one.jeeves-campaign.jsonl",
        "manifest_sha256": None,
        "recheck_original_source": False,
        "tasks": [{
            "task_id": "first", "depends_on": [],
            "target": "/owner/private/first.source.json",
            "expected_job_sha256": digest,
            "native_request": native,
        }],
    }


class OperatorStateTests(unittest.TestCase):
    def setUp(self):
        self.request = original_request()
        self.raw = _canonical(self.request)
        self.owner = operator.NativeCampaignOperator()

    def preview(self):
        receipt = self.owner.inspect(self.raw)
        self.assertEqual(receipt["status"],
                         "review-required-before-original-native-campaign")
        self.assertEqual(receipt["task_count"], 1)
        self.assertEqual(self.owner.approved_manifest, receipt["manifest_sha256"])
        return receipt

    def test_original_review_without_model_or_write(self):
        with mock.patch.object(campaign, "execute_escrow_request") as model:
            inspected = self.preview()
            model.assert_not_called()
        self.assertFalse(inspected["model_started"])
        self.assertFalse(self.owner.native_launch_consumed)

    def test_unreviewed_native_run_cannot_start(self):
        with mock.patch.object(operator, "execute_campaign_request") as execute:
            with self.assertRaises(operator.NativeCampaignOperatorHold):
                self.owner.run(
                    self.raw, typed_manifest_sha256=A,
                    approve_campaign=True, approve_native=True,
                    approve_private_storage=True,
                )
            execute.assert_not_called()

    def test_full_sha_and_three_independent_real_model_grants_required(self):
        checked = self.preview()
        for kwargs in (
            {"typed_manifest_sha256": A, "approve_campaign": True,
             "approve_native": True, "approve_private_storage": True},
            {"typed_manifest_sha256": checked["manifest_sha256"],
             "approve_campaign": False, "approve_native": True,
             "approve_private_storage": True},
            {"typed_manifest_sha256": checked["manifest_sha256"],
             "approve_campaign": True, "approve_native": False,
             "approve_private_storage": True},
            {"typed_manifest_sha256": checked["manifest_sha256"],
             "approve_campaign": True, "approve_native": True,
             "approve_private_storage": False},
        ):
            with self.subTest(kwargs=kwargs):
                with mock.patch.object(operator, "execute_campaign_request") as execute:
                    with self.assertRaises(operator.NativeCampaignOperatorHold):
                        self.owner.run(self.raw, **kwargs)
                    execute.assert_not_called()
        self.assertFalse(self.owner.native_launch_consumed)

    def test_changed_original_model_goal_denied_after_inspection(self):
        self.preview()
        changed = original_request()
        changed["tasks"][0]["native_request"]["goal"] += " extra"
        with mock.patch.object(operator, "execute_campaign_request") as engine:
            with self.assertRaises(operator.NativeCampaignOperatorHold):
                self.owner.run(
                    _canonical(changed),
                    typed_manifest_sha256=self.owner.approved_manifest,
                    approve_campaign=True, approve_native=True,
                    approve_private_storage=True,
                )
            engine.assert_not_called()

    def test_once_only_even_if_actual_native_result_uncertain(self):
        inspected = self.preview()
        with mock.patch.object(operator, "execute_campaign_request",
                               side_effect=RuntimeError("unknown model commit")) as execute:
            with self.assertRaises(RuntimeError):
                self.owner.run(
                    self.raw,
                    typed_manifest_sha256=inspected["manifest_sha256"],
                    approve_campaign=True, approve_native=True,
                    approve_private_storage=True,
                )
            self.assertTrue(self.owner.native_launch_consumed)
            with self.assertRaises(operator.NativeCampaignOperatorHold):
                self.owner.run(
                    self.raw,
                    typed_manifest_sha256=inspected["manifest_sha256"],
                    approve_campaign=True, approve_native=True,
                    approve_private_storage=True,
                )
            execute.assert_called_once()

    def test_native_call_may_commit_at_most_once_per_operator_window(self):
        reviewed = self.preview()
        with mock.patch.object(
            operator, "execute_campaign_request",
            return_value={"status": "native-campaign-held-no-auto-retry"},
        ) as execute:
            result = self.owner.run(
                self.raw,
                typed_manifest_sha256=reviewed["manifest_sha256"],
                approve_campaign=True, approve_native=True,
                approve_private_storage=True,
            )
        self.assertEqual(result["status"], "native-campaign-held-no-auto-retry")
        self.assertTrue(self.owner.native_launch_consumed)
        native = execute.call_args.args[0]
        self.assertEqual(native["action"], "run")
        self.assertEqual(native["manifest_sha256"], reviewed["manifest_sha256"])
        self.assertFalse(native["recheck_original_source"])
        self.assertIs(execute.call_args.kwargs["approve_private_storage"], True)

    def test_cold_verify_can_inspect_without_reissuing_native(self):
        reviewed = self.preview()
        cold = self.owner._verified_request(self.raw, recheck_original=True)
        self.assertEqual(cold["manifest_sha256"], reviewed["manifest_sha256"])
        self.assertEqual(cold["action"], "verify")
        with mock.patch.object(operator, "execute_campaign_request",
                               return_value={"status": "complete"}) as work:
            result = self.owner.verify(self.raw, recheck_original=True)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(work.call_args.args[0]["action"], "verify")

    def test_assembly_reuses_original_cold_source_approval_not_native(self):
        reviewed = self.preview()
        response = {
            "status": "combined-native-source-reviewed-no-write",
            "assembly_sha256": A,
            "combined_source_manifest_sha256": B,
            "combined_patch_sha256": C,
        }
        with mock.patch.object(operator, "execute_delivery_request",
                               return_value={"review": response}) as deliver:
            result = self.owner.inspect_assembly(self.raw)
        self.assertEqual(result, response)
        self.assertEqual(deliver.call_args.args[0]["campaign"]["action"], "verify")
        self.assertEqual(deliver.call_args.args[0]["campaign"]["manifest_sha256"],
                         reviewed["manifest_sha256"])
        self.assertTrue(deliver.call_args.args[0]["campaign"]["recheck_original_source"])

    def test_cannot_publish_without_independently_reviewed_assembly(self):
        self.preview()
        with mock.patch.object(operator, "execute_delivery_request") as deliver:
            with self.assertRaises(operator.NativeCampaignOperatorHold):
                self.owner.publish(
                    self.raw, destination="/owner/private/work.patch",
                    output_kind="git-patch",
                    assembly_sha256=A, source_manifest_sha256=B,
                    patch_sha256=C,
                    approve_private_stage=False, approve_git_patch=True,
                )
            deliver.assert_not_called()

    def test_cannot_publish_with_wrong_sha_or_two_output_grants(self):
        self.preview()
        response = {
            "status": "combined-native-source-reviewed-no-write",
            "assembly_sha256": A, "combined_source_manifest_sha256": B,
            "combined_patch_sha256": C,
        }
        with mock.patch.object(operator, "execute_delivery_request",
                               return_value={"review": response}):
            self.owner.inspect_assembly(self.raw)
        for kwargs in (
            {"assembly_sha256": B, "source_manifest_sha256": B,
             "patch_sha256": C, "approve_private_stage": False,
             "approve_git_patch": True},
            {"assembly_sha256": A, "source_manifest_sha256": B,
             "patch_sha256": C, "approve_private_stage": True,
             "approve_git_patch": True},
        ):
            with self.subTest(kwargs=kwargs):
                with mock.patch.object(operator, "execute_delivery_request") as deliver:
                    with self.assertRaises(operator.NativeCampaignOperatorHold):
                        self.owner.publish(
                            self.raw, destination="/owner/private/work.patch",
                            output_kind="git-patch", **kwargs,
                        )
                    deliver.assert_not_called()

    def test_approved_patch_publication_once_only_even_if_uncertain(self):
        self.preview()
        body = {
            "status": "combined-native-source-reviewed-no-write",
            "assembly_sha256": A, "combined_source_manifest_sha256": B,
            "combined_patch_sha256": C,
        }
        with mock.patch.object(operator, "execute_delivery_request",
                               return_value={"review": body}):
            self.owner.inspect_assembly(self.raw)
        arguments = {
            "destination": "/owner/private/work.patch",
            "output_kind": "git-patch",
            "assembly_sha256": A, "source_manifest_sha256": B,
            "patch_sha256": C,
            "approve_private_stage": False, "approve_git_patch": True,
        }
        with mock.patch.object(operator, "execute_delivery_request",
                               side_effect=RuntimeError("unknown custody")) as deliver:
            with self.assertRaises(RuntimeError):
                self.owner.publish(self.raw, **arguments)
            with self.assertRaises(operator.NativeCampaignOperatorHold):
                self.owner.publish(self.raw, **arguments)
            deliver.assert_called_once()

    def test_owner_reset_discards_approval_not_authoritative_sqlite(self):
        self.preview()
        self.owner.reset()
        self.assertIsNone(self.owner.approved_manifest)
        with self.assertRaises(operator.NativeCampaignOperatorHold):
            self.owner.verify(self.raw, recheck_original=True)


class CampaignWindowSingleOwnerTests(unittest.TestCase):
    def test_desktop_guard_blocks_additional_gguf_owner_in_campaign(self):
        fake = SimpleNamespace(
            _owner=SimpleNamespace(
                _bridge=SimpleNamespace(connected=False),
                _connecting=None, _busy=False,
            ),
        )
        self.assertTrue(ui.NativeCampaignWindow._native_owner_available(fake))
        fake._owner._bridge.connected = True
        self.assertFalse(ui.NativeCampaignWindow._native_owner_available(fake))
        fake._owner._bridge.connected = False
        fake._owner._busy = True
        self.assertFalse(ui.NativeCampaignWindow._native_owner_available(fake))

    def test_native_campaign_opens_only_one_window_on_desktop(self):
        fake = SimpleNamespace(_native_campaign_window=None)
        with mock.patch.object(ui, "NativeCampaignWindow") as ctor:
            # Desktop import occurs inside the action; intercept at the
            # owner module where it resolves the one concrete class.
            with mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_campaign_ui.NativeCampaignWindow",
                return_value=SimpleNamespace(lift=lambda: None, focus_set=lambda: None),
            ) as create:
                desktop_app.JeevesWindow._native_campaign(fake)
                desktop_app.JeevesWindow._native_campaign(fake)
                create.assert_called_once_with(fake)


if __name__ == "__main__":
    unittest.main()
