"""Read-only native task composer tests against actual project source descriptors.

No synthetic model is claimed real. The existing native read-only source
inspector is used; only safety probes mock dynamic file mutations.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_campaign_composer as composer,
    desktop_campaign_composer_ui as composer_ui,
    desktop_campaign_ui as campaign_ui,
    desktop_native_campaign as campaign,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli import (
    execute_native_request,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace import _canonical


class ComposerFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir(mode=0o700)
        self.project.chmod(0o700)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.model = self.root / "model"
        self.state = self.root / "state"
        (self.project / "pkg").mkdir(mode=0o700)
        (self.project / "pkg").chmod(0o700)

    def record(self, names=("first", "second"), sources=()):
        return {
            "schema": composer.SCHEMA,
            "project_root": str(self.project),
            "private_dir": str(self.private),
            "journal_name": "test.jeeves-campaign.jsonl",
            "model_root": str(self.model),
            "state_dir": str(self.state),
            "tenant": "local", "subject": "owner",
            "context_tokens": 2048, "max_output_tokens": 256,
            "threads": 2, "gpu_layers": 0, "inference_ms": 2500,
            "capacity_budget_bytes": 2**30,
            "tasks": [
                {
                    "task_id": name,
                    "depends_on": [names[i - 1]] if i else [],
                    "goal": "Author an original runnable module for " + name,
                    "format": "new-files", "maximum_attempts": 1,
                    "source_paths": list(sources),
                    "target_name": name + ".source.json",
                } for i, name in enumerate(names)
            ],
        }

    def compose(self, names=("first", "second"), sources=()):
        return composer.compose_campaign(_canonical(self.record(names, sources)))


class ComposerSourceTests(ComposerFixture):
    def test_real_readonly_source_goals_to_two_digest_bound_native_tasks(self):
        with mock.patch.object(campaign, "execute_escrow_request") as real_model:
            private, public = self.compose()
            real_model.assert_not_called()
        self.assertEqual(public["task_count"], 2)
        self.assertEqual(public["status"], "original-source-campaign-composed-no-model")
        self.assertFalse(public["model_started"])
        self.assertFalse(public["project_files_modified"])
        self.assertEqual(private["action"], "inspect")
        self.assertEqual(private["tasks"][1]["depends_on"], ["first"])
        for task in private["tasks"]:
            self.assertEqual(task["native_request"]["action"], "generate")
            self.assertEqual(
                task["native_request"]["job_sha256"],
                task["expected_job_sha256"],
            )
            self.assertEqual(len(task["expected_job_sha256"]), 64)
            self.assertFalse(Path(task["target"]).exists())
        self.assertFalse((self.private / "test.jeeves-campaign.jsonl").exists())
        self.assertEqual(
            campaign.inspect_campaign(campaign.parse_campaign(_canonical(private))[0])[
                "manifest_sha256"
            ], public["manifest_sha256"],
        )

    def test_selected_original_python_source_sha_is_in_both_task_identities(self):
        sample = self.project / "pkg" / "existing.py"
        sample.write_text("ORIGINAL = 7\n", encoding="utf-8")
        sample.chmod(0o600)
        private, public = self.compose(("first",), sources=("pkg/existing.py",))
        native = private["tasks"][0]["native_request"]
        self.assertEqual(public["source_snapshot_count"], 1)
        self.assertEqual(len(native["source_context_sha256"]), 64)
        self.assertEqual(
            native["source_context_sha256"],
            execute_native_request({
                **native, "action": "inspect", "job_sha256": None,
            })["source_context_sha256"],
        )
        self.assertEqual(sample.read_text(), "ORIGINAL = 7\n")

    def test_model_and_private_goals_never_disclosed_into_public_receipt(self):
        private, result = self.compose(names=("secret-goal",))
        text = json.dumps(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("Author an original runnable module", text)
        self.assertNotIn("secret-goal", text)
        self.assertFalse(result["private_goals_and_paths_emitted_to_stdout"])
        self.assertNotEqual(private["tasks"][0]["native_request"]["goal"], "")

    def test_duplicate_task_targets_or_backwards_dependencies_hold(self):
        request = self.record()
        request["tasks"][1]["target_name"] = "first.source.json"
        with self.assertRaises(composer.CampaignComposerHold):
            composer.compose_campaign(_canonical(request))
        request = self.record()
        request["tasks"][0]["depends_on"] = ["second"]
        with self.assertRaises((ValueError, composer.CampaignComposerHold)):
            composer.compose_campaign(_canonical(request))

    def test_private_output_directory_cannot_be_under_project_or_model(self):
        for path in (
            str(self.project / "private"), str(self.model / "escrows"),
            str(self.state / "escrows"), str(self.root),
        ):
            with self.subTest(path=path):
                request = self.record()
                request["private_dir"] = path
                with self.assertRaises(composer.CampaignComposerHold):
                    composer.compose_campaign(_canonical(request))

    def test_private_journal_or_target_traversal_cannot_be_constructed(self):
        for key, value in (
            ("journal_name", "../original.jeeves-campaign.jsonl"),
            ("journal_name", "/tmp/original.jeeves-campaign.jsonl"),
        ):
            with self.subTest(key=key, value=value):
                request = self.record()
                request[key] = value
                with self.assertRaises(composer.CampaignComposerHold):
                    composer.compose_campaign(_canonical(request))
        for target in ("../evil.source.json", "pkg/a.source.json",
                       "token.txt", ".git.source.json"):
            with self.subTest(target=target):
                request = self.record()
                request["tasks"][0]["target_name"] = target
                with self.assertRaises((ValueError, composer.CampaignComposerHold)):
                    composer.compose_campaign(_canonical(request))

    def test_missing_unknown_duplicate_and_nonfinite_json_are_denied(self):
        malformed = self.record()
        malformed["tool_grant"] = "execute-code"
        with self.assertRaises(composer.CampaignComposerHold):
            composer.parse_composer_request(_canonical(malformed))
        raw = _canonical(self.record())
        with self.assertRaises(composer.CampaignComposerHold):
            composer.parse_composer_request(
                raw.replace(b'"schema":', b'"schema":"forged","schema":', 1),
            )
        with self.assertRaises(composer.CampaignComposerHold):
            composer.parse_composer_request(
                raw.replace(b'"threads":2', b'"threads":NaN', 1),
            )

    def test_native_source_budgets_cannot_be_bypassed_through_composer(self):
        for key, value in (
            ("max_output_tokens", 99999),
            ("context_tokens", 64),
            ("gpu_layers", 17),
            ("inference_ms", -1),
            ("threads", 0),
        ):
            with self.subTest(key=key, value=value):
                request = self.record()
                request[key] = value
                with self.assertRaises((ValueError, composer.CampaignComposerHold)):
                    composer.compose_campaign(_canonical(request))

    def test_oversized_aggregate_native_task_count_or_goals_hold(self):
        with self.assertRaises(composer.CampaignComposerHold):
            composer.parse_composer_request(
                _canonical(self.record(names=tuple("abcdefghijklm"))),
            )
        request = self.record()
        request["tasks"][0]["goal"] = "a" * (composer.MAX_GOAL_BYTES + 1)
        with self.assertRaises(composer.CampaignComposerHold):
            composer.parse_composer_request(_canonical(request))

    def test_existing_private_target_is_held_before_model_or_journal(self):
        occupied = self.private / "first.source.json"
        occupied.write_text("human-owned")
        raw = occupied.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.compose()
        self.assertEqual(occupied.read_bytes(), raw)
        self.assertFalse((self.private / "test.jeeves-campaign.jsonl").exists())

    def test_existing_private_journal_is_held_without_reusing_prior_state(self):
        journal = self.private / "test.jeeves-campaign.jsonl"
        journal.write_text('{"human":"owner"}\n')
        with self.assertRaises((ValueError, OSError)):
            self.compose()
        self.assertIn("human", journal.read_text())

    def test_original_source_mutation_during_review_denied(self):
        src = self.project / "pkg" / "existing.py"
        src.write_text("ORIGINAL=5\n")
        src.chmod(0o600)
        actual = composer.execute_native_request
        count = [0]
        def modified(req, **kwargs):
            receipt = actual(req, **kwargs)
            count[0] += 1
            if count[0] == 1:
                src.write_text("ORIGINAL=6\n")
            return receipt
        with mock.patch.object(composer, "execute_native_request",
                               side_effect=modified):
            with self.assertRaises((ValueError, composer.CampaignComposerHold)):
                self.compose(names=("first",), sources=("pkg/existing.py",))
        self.assertFalse((self.private / "test.jeeves-campaign.jsonl").exists())


class ComposerDesktopTemplateTests(unittest.TestCase):
    def test_template_uses_user_visible_existing_model_fields(self):
        names = [
            "model_root", "state_dir", "tenant", "subject", "context",
            "max_output_tokens", "threads", "gpu_layers", "inference_ms",
            "capacity_budget_bytes",
        ]
        value = {
            "model_root": "/owner/model", "state_dir": "/owner/state",
            "tenant": "local", "subject": "owner", "context": "4096",
            "max_output_tokens": "512", "threads": "4", "gpu_layers": "0",
            "inference_ms": "90000", "capacity_budget_bytes": "1000000000",
        }
        fields = {key: SimpleNamespace(get=lambda name=key: value[name]) for key in names}
        stub = SimpleNamespace(fields=fields)
        parsed = json.loads(composer_ui.default_composer_template(stub))
        self.assertEqual(parsed["threads"], 4)
        self.assertEqual(parsed["max_output_tokens"], 512)
        self.assertEqual(parsed["model_root"], "/owner/model")
        self.assertEqual(parsed["project_root"], "")
        self.assertEqual(parsed["private_dir"], "")
        self.assertEqual(parsed["tasks"][0]["format"], "new-files")
        self.assertFalse(parsed["tasks"][0]["source_paths"])


if __name__ == "__main__":
    unittest.main()
