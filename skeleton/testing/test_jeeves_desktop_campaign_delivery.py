"""Integration tests for multiple REAL-native-shaped, independently saved source tasks.

Native model calls and private GGUF escrow are replaced with exact typed
receipts. Actual source parse/merge, Git-diff rendering, private staging,
descriptor reads, and final cold publication are real filesystem operations.
These tests are source-only, never evidence of a physical GGUF device run.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_campaign_delivery as delivery,
    desktop_campaign_delivery_cli as cli,
    desktop_native_campaign as campaign,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli import (
    SCHEMA as NATIVE_SCHEMA, execute_native_request,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery import (
    ReviewedNativeDelivery,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_patch_bundle import (
    review_patch_bundle,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_source_graph import (
    analyze_python_source_graph,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_source_qualification import (
    require_parseable_patch,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace import (
    SCHEMA as NEW_SCHEMA, _canonical,
)


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


class SourceAssemblyFixture(unittest.TestCase):
    def setUp(self):
        # The production no-follow root reader rejects group/world-writable
        # ancestors (including /tmp), not just the final project directory.
        # Use an owner-controlled home ancestor rather than weakening it.
        temp = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "project"
        self.project.mkdir(mode=0o700)
        self.project.chmod(0o700)
        (self.project / "pkg").mkdir(mode=0o700)
        (self.project / "pkg").chmod(0o700)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.journal_file = self.private / "native.jeeves-campaign.jsonl"

    def plan(self, names=("one", "two")):
        tasks = []
        for index, name in enumerate(names):
            native = {
                "schema": NATIVE_SCHEMA, "action": "inspect",
                "project_root": str(self.project),
                "model_root": str(self.root / "model"),
                "state_dir": str(self.root / "state"),
                "tenant": "owner", "subject": "local",
                "goal": name + " original coding goal", "format": "new-files",
                "maximum_attempts": 1,
                "source_paths": [], "source_context_sha256": None,
                "job_sha256": None,
                "context_tokens": 1024, "max_output_tokens": 128,
                "threads": 1, "gpu_layers": 0, "inference_ms": 1000,
                "capacity_budget_bytes": 2**30,
            }
            digest = execute_native_request(native)["job_sha256"]
            native["action"] = "generate"
            native["job_sha256"] = digest
            tasks.append({
                "task_id": name, "depends_on": [names[index - 1]] if index else [],
                "target": str(self.private / (name + ".source.json")),
                "expected_job_sha256": digest,
                "native_request": native,
            })
        value = {
            "schema": campaign.SCHEMA, "action": "inspect",
            "project_root": str(self.project),
            "journal_file": str(self.journal_file),
            "manifest_sha256": None, "recheck_original_source": False,
            "tasks": tasks,
        }
        plan, _ = campaign.parse_campaign(_canonical(value))
        return plan

    def make_source_plan(self, path, text):
        return review_patch_bundle(
            str(self.project),
            new_files=_canonical({
                "schema": NEW_SCHEMA,
                "files": [{"path": path, "content": text}],
            }),
        )

    def saved(self, job, original_source_plan, file_sha, file_bytes=128):
        graph = analyze_python_source_graph(original_source_plan)
        static = require_parseable_patch(original_source_plan)
        return ReviewedNativeDelivery(
            job_sha256=job, private_file_sha256=file_sha,
            source_manifest_sha256=original_source_plan.manifest_sha256,
            patch_sha256=original_source_plan.patch_sha256,
            model_sha256=C,
            python_graph_sha256=graph.graph_sha256,
            private_file_bytes=file_bytes,
            source_plan=original_source_plan,
            static_status=static.status,
        )

    def mock_campaign(self, plan, *, files=None):
        if files is None:
            files = (("pkg/a.py", "from pkg import b\n"),
                     ("pkg/b.py", "value = 123\n"))
        reviewed = [
            self.saved(task.expected_job_sha256,
                       self.make_source_plan(*files[index]),
                       A if index == 0 else B)
            for index, task in enumerate(plan.tasks)
        ]
        audit = {
            "all_tasks_completed": True,
            "last_event_sha256": D,
            "saved_receipts": {
                task.task_id: {
                    "job_sha256": task.expected_job_sha256,
                    "private_file_sha256": review.private_file_sha256,
                    "private_file_bytes": review.private_file_bytes,
                    "model_sha256": review.model_sha256,
                    "session_id": "sqlite-" + task.task_id,
                    "source_manifest_sha256": review.source_manifest_sha256,
                    "source_patch_sha256": review.patch_sha256,
                }
                for task, review in zip(plan.tasks, reviewed)
            },
        }
        def fetch(path, **kwargs):
            item = next(j for j, t in enumerate(plan.tasks) if t.target == path)
            self.assertEqual(kwargs["expected_job_sha256"],
                             plan.tasks[item].expected_job_sha256)
            return reviewed[item]
        return (
            mock.patch.object(delivery, "verify_campaign",
                              return_value={"all_source_escrows_cold_verified": True}),
            mock.patch.object(delivery, "inspect_campaign_journal",
                              return_value=audit),
            mock.patch.object(delivery, "inspect_saved_native_source",
                              side_effect=fetch),
        )


class ReviewedCampaignAssemblyTests(SourceAssemblyFixture):
    def test_two_native_source_tasks_join_one_real_patch_with_cross_import(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        with a, b, c:
            assembled = delivery.inspect_campaign_assembly(plan)
        view = assembled.public_review()
        self.assertEqual(view["native_task_count"], 2)
        self.assertEqual(view["merged_source_count"], 2)
        self.assertEqual(view["new_source_files"], 2)
        self.assertEqual(view["existing_source_edits"], 0)
        self.assertEqual(view["assembly_sha256"], assembled.assembly_sha256)
        self.assertEqual(
            analyze_python_source_graph(assembled.patch).linked_import_count, 1,
        )
        self.assertFalse(view["native_code_executed"])
        self.assertNotIn("value = 123", json.dumps(view))
        self.assertNotIn(str(self.project), json.dumps(view))

    def test_cross_task_duplicate_path_denied_no_model_wins_by_order(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(
            plan, files=(("pkg/a.py", "x = 1\n"),
                         ("pkg/a.py", "x = 2\n")),
        )
        with a, b, c:
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.inspect_campaign_assembly(plan)

    def test_mixed_model_identity_is_rejected_even_if_each_saved_source_valid(self):
        plan = self.plan()
        reviewed = self.mock_campaign(plan)
        a, b, c = reviewed
        with a, b, c as fetch:
            original = fetch.side_effect
            def mixed(path, **kwargs):
                value = original(path, **kwargs)
                return replace(value, model_sha256=D) if path == plan.tasks[1].target else value
            fetch.side_effect = mixed
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.inspect_campaign_assembly(plan)

    def test_missing_native_escrow_halts_combined_source_review(self):
        plan = self.plan()
        with mock.patch.object(delivery, "verify_campaign",
                               return_value={"all_source_escrows_cold_verified": False}), \
             mock.patch.object(delivery, "inspect_saved_native_source") as fetch:
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.inspect_campaign_assembly(plan)
            fetch.assert_not_called()

    def test_unresolved_native_campaign_cannot_promote_saved_source(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        with a, b as audit, c:
            original = audit.return_value
            audit.return_value = {**original, "all_tasks_completed": False}
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.inspect_campaign_assembly(plan)

    def test_combined_manifest_is_stable_under_exact_input_order(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        with a, b, c:
            first = delivery.inspect_campaign_assembly(plan)
            second = delivery.inspect_campaign_assembly(plan)
        self.assertEqual(first.assembly_sha256, second.assembly_sha256)
        self.assertEqual(first.combined_patch_sha256, second.combined_patch_sha256)

    def test_change_in_native_audit_digest_invalidates_final_assembly(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        with a, b as audit, c:
            first = delivery.inspect_campaign_assembly(plan)
            audit.return_value = {
                **audit.return_value, "last_event_sha256": "e" * 64,
            }
            second = delivery.inspect_campaign_assembly(plan)
        self.assertNotEqual(first.assembly_sha256, second.assembly_sha256)

    def test_forbidden_unreviewed_approval_hash_rejects_publication(self):
        plan = self.plan()
        with mock.patch.object(delivery, "inspect_campaign_assembly") as inspect:
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.publish_campaign_assembly(
                    plan, str(self.private / "combined.patch"),
                    output_kind="git-patch", expected_assembly_sha256=A,
                    expected_manifest_sha256=B, expected_patch_sha256=C,
                    approve_delivery=False,
                )
            inspect.assert_not_called()

    def test_stale_assembly_sha_blocks_without_creating_output(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        target = self.private / "combined.patch"
        with a, b, c:
            info = delivery.inspect_campaign_assembly(plan)
            with self.assertRaises(delivery.CampaignAssemblyHold):
                delivery.publish_campaign_assembly(
                    plan, str(target), output_kind="git-patch",
                    expected_assembly_sha256=A,
                    expected_manifest_sha256=info.combined_source_manifest_sha256,
                    expected_patch_sha256=info.combined_patch_sha256,
                    approve_delivery=True,
                )
        self.assertFalse(target.exists())

    def test_real_private_git_patch_and_separate_cold_verify(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        target = self.private / "merged.patch"
        with a, b, c:
            info = delivery.inspect_campaign_assembly(plan)
            result = delivery.publish_campaign_assembly(
                plan, str(target), output_kind="git-patch",
                expected_assembly_sha256=info.assembly_sha256,
                expected_manifest_sha256=info.combined_source_manifest_sha256,
                expected_patch_sha256=info.combined_patch_sha256,
                approve_delivery=True,
            )
        self.assertEqual(result["status"], "new-cold-verified-multi-task-source-delivery")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        patch = target.read_text()
        self.assertIn("diff --git a/pkg/a.py b/pkg/a.py", patch)
        self.assertIn("diff --git a/pkg/b.py b/pkg/b.py", patch)
        self.assertFalse((self.project / "pkg" / "a.py").exists())

    def test_real_private_source_overlay_contains_both_task_replacements(self):
        plan = self.plan()
        a, b, c = self.mock_campaign(plan)
        target = self.private / "merged_stage"
        with a, b, c:
            info = delivery.inspect_campaign_assembly(plan)
            result = delivery.publish_campaign_assembly(
                plan, str(target), output_kind="private-stage",
                expected_assembly_sha256=info.assembly_sha256,
                expected_manifest_sha256=info.combined_source_manifest_sha256,
                expected_patch_sha256=info.combined_patch_sha256,
                approve_delivery=True,
            )
        self.assertEqual(result["output_kind"], "private-stage")
        self.assertEqual(
            (target / "changes" / "pkg" / "b.py").read_text(),
            "value = 123\n",
        )
        self.assertEqual((target / "seal.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.project / "pkg" / "b.py").exists())


class CampaignAssemblyCommandTests(SourceAssemblyFixture):
    def req(self, kind="inspect", action="inspect"):
        plan = self.plan()
        campaign_request = {
            "schema": campaign.SCHEMA, "action": "verify",
            "project_root": plan.project_root,
            "journal_file": plan.journal_file,
            "manifest_sha256": plan.manifest_sha256,
            "recheck_original_source": True,
            "tasks": [task.document() for task in plan.tasks],
        }
        return {
            "schema": cli.SCHEMA,
            "action": action,
            "campaign": campaign_request,
            "output_kind": kind if action == "publish" else None,
            "destination": str(self.private / "combined.patch") if action == "publish" else None,
            "assembly_sha256": A if action == "publish" else None,
            "source_manifest_sha256": B if action == "publish" else None,
            "patch_sha256": C if action == "publish" else None,
        }

    def test_strict_readonly_and_private_publish_shapes(self):
        self.assertEqual(cli.parse_delivery_request(_canonical(self.req()))["action"],
                         "inspect")
        self.assertEqual(cli.parse_delivery_request(
            _canonical(self.req("git-patch", "publish")),
        )["output_kind"], "git-patch")

    def test_unexpected_and_duplicate_json_keys_fail_closed(self):
        value = self.req()
        value["unknown_model_tool_grant"] = True
        with self.assertRaises(cli.CampaignDeliveryCLIHold):
            cli.parse_delivery_request(_canonical(value))
        raw = _canonical(self.req())
        with self.assertRaises(cli.CampaignDeliveryCLIHold):
            cli.parse_delivery_request(
                raw.replace(b'"action":"inspect"',
                            b'"action":"inspect","action":"publish"', 1),
            )

    def test_readonly_inspection_rejects_source_write_flags(self):
        value = self.req()
        with self.assertRaises(cli.CampaignDeliveryCLIHold):
            cli.execute_delivery_request(value, approve_git_patch=True)

    def test_private_stage_requires_correct_flag_not_git_patch_flag(self):
        value = self.req("private-stage", "publish")
        with mock.patch.object(cli, "publish_campaign_assembly") as work:
            for grant in ({}, {"approve_git_patch": True}):
                with self.assertRaises(cli.CampaignDeliveryCLIHold):
                    cli.execute_delivery_request(value, **grant)
            work.assert_not_called()

    def test_refused_cli_never_leaks_private_paths(self):
        value = self.req("git-patch", "publish")
        output = io.StringIO()
        error = io.StringIO()
        rc = cli.main(
            [], stdin=io.BytesIO(_canonical(value)),
            stdout=output, stderr=error,
        )
        self.assertEqual(rc, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "JEEVES_CAMPAIGN_SOURCE_DELIVERY_HELD\n")
        self.assertNotIn(str(self.project), error.getvalue())


if __name__ == "__main__":
    unittest.main()
