"""Offline headless Jeeves source review, sealed overlay and patch CLI tests.

Run after implementation; all calls use disposable original source/preview
files and synthetic operator requests. No generated code, real model, Git
commands or cloud service is ever executed.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_work_cli as cli,
    desktop_patch_bundle as bundle,
    desktop_patch_export as export,
    desktop_private_overlay as overlay,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
    desktop_project_work as mixed,
    desktop_patch_reconcile as reconcile,
)

SCHEMA = cli.SCHEMA


def new_source(path="src/new.py", text="def new():\n    return 42\n"):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": path, "content": text}],
    })


def edited_source(path="src/existing.py", original="old=1\n", changed="old=2\n"):
    return json.dumps({
        "schema": edits.SCHEMA,
        "files": [{
            "path": path,
            "expected_sha256": sha256(original.encode()).hexdigest(),
            "replacement": changed,
        }],
    })


def request(*, root="/private/original", action="review",
            new_files=None, existing_edits=None, mixed_work=None,
            target=None, manifest=None, patch=None, patch_bytes=None):
    return {
        "schema": SCHEMA,
        "action": action,
        "root": str(root),
        "new_files": new_files,
        "existing_edits": existing_edits,
        "mixed_work": mixed_work,
        "target": str(target) if target is not None else None,
        "source_manifest_sha256": manifest,
        "patch_sha256": patch,
        "patch_bytes": patch_bytes,
    }


class StrictCLIParserTests(unittest.TestCase):
    def test_request_rejects_unknown_escalated_authority(self):
        valid = request(new_files=new_source())
        self.assertEqual(
            cli.parse_request(json.dumps(valid).encode())["action"], "review",
        )
        bad = (
            dict(valid, shell=True),
            dict(valid, action="exec"),
            dict(valid, action="run-inference"),
            dict(valid, action="merge-to-main"),
            dict(valid, root="../relative"),
            dict(valid, root="/tmp/private/../changed"),
            dict(valid, source_manifest_sha256="a"*64),
            dict(valid, new_files=None),
            dict(valid, mixed_work=new_source()),
            dict(valid, patch_bytes=True),
            dict(valid, target="/tmp/fake-private-output.patch"),
        )
        for entry in bad:
            with self.subTest(entry=repr(entry)[:80]), self.assertRaises(
                cli.LocalSourceCLIHold,
            ):
                cli.parse_request(json.dumps(entry).encode())

    def test_duplicate_forged_json_nonfinite_untyped_and_oversize_are_held(self):
        for raw in (
            b"{}",
            b"",
            b"x" * (cli.MAX_REQUEST_BYTES + 1),
            b'{"schema":NaN}',
            b'{"action":"review","action":"stage"}',
            b'\xff',
            b"[]",
        ):
            with self.subTest(raw=raw[:40]), self.assertRaises(cli.LocalSourceCLIHold):
                cli.parse_request(raw)

    def test_verification_request_cannot_carry_source_or_output_grants(self):
        base = request(
            action="verify-stage", root="/private/project",
            manifest="a"*64, patch="b"*64,
            target="/private/stages/one",
        )
        self.assertEqual(
            cli.parse_request(json.dumps(base).encode())["action"],
            "verify-stage",
        )
        for changed in (
            {"new_files": new_source()},
            {"action": "verify-patch"},
            {"target": None},
            {"patch_bytes": 50},
            {"source_manifest_sha256": "bad"},
        ):
            with self.subTest(changed=changed), self.assertRaises(cli.LocalSourceCLIHold):
                cli.parse_request(json.dumps({**base, **changed}).encode())


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Headless private source workflows require POSIX/WSL2",
)
class HeadlessSourceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jeeves-headless-cli-")
        self.addCleanup(self.tmp.cleanup)
        self.top = Path(self.tmp.name)
        self.project = self.top / "project"
        self.project.mkdir(mode=0o700)
        (self.project / "src").mkdir(mode=0o700)
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self.stage = self.private / "stageA"
        self.patch_target = self.private / "reviewed.patch"
        self.original = "old=1\n"
        self.original_path = self.project / "src/existing.py"
        self.original_path.write_text(self.original, encoding="utf-8")

        def test_root(value):
            return os.open(value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for module in (workspace, edits, bundle, reconcile):
            patched = mock.patch.object(
                module, "_open_root", side_effect=test_root,
            )
            patched.start()
            self.addCleanup(patched.stop)
        for module in (overlay, export):
            patched = mock.patch.object(
                module, "_pinned_private_directory",
                side_effect=lambda path: test_root(path.parent),
            )
            patched.start()
            self.addCleanup(patched.stop)

    def proposal(self):
        return request(
            root=self.project, new_files=new_source(),
            existing_edits=edited_source(),
        )

    def reviewed(self):
        result = cli.execute(self.proposal())
        self.assertEqual(result["status"], "original-source-reviewed")
        self.assertEqual(result["qualification"]["status"], "parse-clean")
        return result

    def write_request(self, action="stage", *, target=None):
        result = self.reviewed()["review"]
        return request(
            root=self.project,
            action=action,
            new_files=new_source(),
            existing_edits=edited_source(),
            target=target or (
                self.stage if action == "stage" else self.patch_target
            ),
            manifest=result["manifest_sha256"],
            patch=result["patch_sha256"],
        )

    def test_review_reports_exact_full_patch_with_no_untrusted_source_contents(self):
        with (
            mock.patch("subprocess.Popen") as subprocess,
            mock.patch("subprocess.run") as run,
        ):
            result = self.reviewed()
        subprocess.assert_not_called()
        run.assert_not_called()
        public = result["review"]
        self.assertEqual(public["file_count"], 2)
        self.assertEqual(public["new_files"], 1)
        self.assertEqual(public["existing_edits"], 1)
        self.assertEqual(result["qualification"]["file_count"], 2)
        self.assertEqual(result["python_source_graph"]["status"],
                         "observed-internal-imports")
        self.assertEqual(len(result["python_source_graph"]["graph_sha256"]), 64)
        self.assertFalse(
            result["python_source_graph"]["all_dependencies_resolved"],
        )
        self.assertEqual(public["manifest_sha256"],
                         result["qualification"]["source_manifest_sha256"])
        self.assertEqual(public["patch_sha256"],
                         result["qualification"]["source_patch_sha256"])
        self.assertFalse(result["source_code_executed"])
        self.assertFalse(result["git_commands_executed"])
        self.assertFalse(result["model_inference_started"])
        self.assertFalse(result["release_certified"])
        self.assertNotIn("def new()", json.dumps(result))
        self.assertNotIn("old=1", json.dumps(result))

    def test_headless_stage_needs_dual_exact_digest_and_separate_flag(self):
        req = self.write_request()
        with self.assertRaises(cli.LocalSourceCLIHold):
            cli.execute(req)
        self.assertFalse(self.stage.exists())
        with self.assertRaises(cli.LocalSourceCLIHold):
            cli.execute(dict(req, patch_sha256="f"*64), approve_private_stage=True)
        self.assertFalse(self.stage.exists())
        result = cli.execute(req, approve_private_stage=True)
        self.assertEqual(result["action"], "stage")
        self.assertEqual(result["operation"]["file_count"], 2)
        self.assertEqual(
            (self.stage / "changes/src/existing.py").read_text(), "old=2\n",
        )
        self.assertEqual(
            (self.stage / "changes/src/new.py").read_text(),
            "def new():\n    return 42\n",
        )
        self.assertEqual(self.original_path.read_text(), "old=1\n")
        self.assertFalse(result["original_checkout_modified"])
        self.assertFalse(result["source_code_executed"])
        self.assertTrue((self.stage / "seal.json").exists())

    def test_read_only_cold_overlay_validation_needs_no_model_request(self):
        req = self.write_request()
        staged = cli.execute(req, approve_private_stage=True)
        exact = request(
            root=self.project, action="verify-stage",
            target=self.stage,
            manifest=req["source_manifest_sha256"],
            patch=req["patch_sha256"],
        )
        verified = cli.execute(exact)
        self.assertEqual(verified["operation"]["metadata_sha256"],
                         staged["operation"]["metadata_sha256"])
        self.assertFalse(verified["model_inference_started"])
        self.assertFalse(verified["git_commands_executed"])
        self.assertEqual(self.original_path.read_text(), "old=1\n")

    def test_patch_export_requires_separate_only_matching_flag(self):
        req = self.write_request(action="export-patch")
        with self.assertRaises(cli.LocalSourceCLIHold):
            cli.execute(req, approve_private_stage=True)
        self.assertFalse(self.patch_target.exists())
        with self.assertRaises(cli.LocalSourceCLIHold):
            cli.execute(req)
        exported = cli.execute(req, approve_private_patch=True)
        self.assertEqual(exported["operation"]["patch_sha256"],
                         req["patch_sha256"])
        self.assertTrue(self.patch_target.is_file())
        self.assertEqual(self.patch_target.stat().st_mode & 0o777, 0o600)
        self.assertFalse(exported["original_checkout_modified"])
        self.assertFalse(exported["operation"]["patch_applied"])
        self.assertFalse(exported["release_certified"])

    def test_cold_saved_git_patch_validation_is_exact_readonly(self):
        req = self.write_request(action="export-patch")
        published = cli.execute(req, approve_private_patch=True)
        verification = request(
            root=self.project, action="verify-patch",
            target=self.patch_target,
            patch=req["patch_sha256"],
            patch_bytes=published["operation"]["bytes"],
        )
        found = cli.execute(verification)
        self.assertEqual(found["operation"]["patch_sha256"],
                         req["patch_sha256"])
        self.assertFalse(found["model_inference_started"])
        self.assertFalse(found["original_checkout_modified"])
        self.assertEqual(self.original_path.read_text(), "old=1\n")

    def test_headless_reconcile_is_review_only_without_project_mutation(self):
        original = self.proposal()
        result = cli.execute(dict(original, action="reconcile"))
        self.assertEqual(result["action"], "reconcile")
        self.assertEqual(result["status"], "source-reconciliation-reviewed")
        self.assertFalse(result["original_checkout_modified"])
        self.assertFalse(result["git_commands_executed"])
        self.assertIsNotNone(result["operation"]["rebase_sha256"])
        self.assertFalse(self.stage.exists())

    def test_mixed_json_is_supported_without_second_model_or_provider(self):
        contents = json.dumps({
            "schema": mixed.SCHEMA,
            "new_files": [{"path": "src/new.py",
                           "content": "def new():\n    return 42\n"}],
            "existing_edits": [{
                "path": "src/existing.py",
                "expected_sha256": sha256(self.original.encode()).hexdigest(),
                "replacement": "old=2\n",
            }],
        })
        original = request(root=self.project, mixed_work=contents)
        result = cli.execute(original)
        self.assertEqual(result["review"]["file_count"], 2)
        self.assertEqual(result["qualification"]["status"], "parse-clean")
        self.assertFalse(result["model_inference_started"])
        self.assertFalse((self.project / "src/new.py").exists())

    def test_headless_source_drift_after_review_is_a_terminal_hold(self):
        req = self.write_request()
        self.original_path.write_text("old=another\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            cli.execute(req, approve_private_stage=True)
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.original_path.read_text(), "old=another\n")

    def test_actual_stdin_main_emits_only_bounded_public_json(self):
        req = self.proposal()
        output = StringIO()
        errors = StringIO()
        code = cli.main(
            [], source=BytesIO(json.dumps(req).encode()),
            output=output, errors=errors,
        )
        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        public = json.loads(output.getvalue())
        self.assertEqual(public["schema"], cli.RESULT_SCHEMA)
        self.assertEqual(public["review"]["file_count"], 2)
        self.assertNotIn("old=1", output.getvalue())
        self.assertNotIn(str(self.project), output.getvalue())

    def test_actual_stdin_write_without_flag_has_zero_effect(self):
        req = self.write_request()
        output = StringIO()
        errors = StringIO()
        code = cli.main(
            [], source=BytesIO(json.dumps(req).encode()),
            output=output, errors=errors,
        )
        self.assertEqual(code, 2)
        self.assertFalse(self.stage.exists())
        self.assertEqual(output.getvalue(), "")
        self.assertIn("held", errors.getvalue())
        self.assertNotIn(str(self.project), errors.getvalue())

    def test_no_error_path_logs_private_source_content(self):
        def corrupt():
            return dict(self.proposal(), new_files="private credential\n")
        output = StringIO()
        errors = StringIO()
        result = cli.main(
            [], source=BytesIO(json.dumps(corrupt()).encode()),
            output=output, errors=errors,
        )
        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("credential", errors.getvalue())
        self.assertNotIn(str(self.project), errors.getvalue())
        self.assertEqual(self.original_path.read_text(), self.original)


if __name__ == "__main__":
    unittest.main()
