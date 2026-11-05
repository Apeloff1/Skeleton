"""Cold saved-native source to a separate operator-approved real source artifact.

These source-only tests exercise private file descriptors and original
source files with exact bytes/hashes. No model or generated Python is ever
executed; the fake source receipt is an explicit synthetic SQLite witness
used only to qualify source custody, not physical GGUF or licensing.
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
    desktop_native_proposal_custody as custody,
    desktop_native_source_delivery as delivery,
    desktop_native_source_delivery_cli as cli,
    desktop_patch_bundle as patch,
    desktop_private_overlay as overlay,
    desktop_patch_export as export,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
    desktop_project_work as mixed,
)

MODEL = "a"*64
JOB = "b"*64
SESSION = "s_checked_native_01"


def mixed_source(original_sha: str) -> str:
    return json.dumps({
        "schema": mixed.SCHEMA,
        "new_files": [
            {"path": "src/helper.py", "content": "def helper():\n    return 42\n"},
        ],
        "existing_edits": [
            {
                "path": "src/app.py",
                "expected_sha256": original_sha,
                "replacement": (
                    "from .helper import helper\n"
                    "def start():\n    return helper()\n"
                ),
            },
        ],
    }, ensure_ascii=False, sort_keys=True)


def delivery_req(
    *, root, escrow, escrow_sha, escrow_bytes,
    action="review", target=None, manifest=None, patch_sha=None,
):
    return {
        "schema": cli.SCHEMA,
        "action": action,
        "project_root": str(root),
        "saved_proposal_file": str(escrow),
        "expected_saved_file_sha256": escrow_sha,
        "expected_saved_file_bytes": escrow_bytes,
        "expected_job_sha256": JOB,
        "target": str(target) if target is not None else None,
        "source_manifest_sha256": manifest,
        "source_patch_sha256": patch_sha,
    }


class StrictNativeDeliveryAdmissionTests(unittest.TestCase):
    def test_cli_schema_rejects_extra_authority_untyped_and_wrong_mode(self):
        valid = delivery_req(
            root="/private/project",
            escrow="/private/review/original.source.json",
            escrow_sha="a"*64, escrow_bytes=123,
        )
        self.assertEqual(
            cli.parse_delivery_request(json.dumps(valid).encode())["action"],
            "review",
        )
        bad = (
            {},
            dict(valid, overwrite=True),
            dict(valid, action="run-code"),
            dict(valid, action=[]),
            dict(valid, project_root="../relative"),
            dict(valid, project_root="/private/../escape"),
            dict(valid, saved_proposal_file="relative.source.json"),
            dict(valid, expected_saved_file_sha256="x"),
            dict(valid, expected_saved_file_bytes=True),
            dict(valid, expected_saved_file_bytes=0),
            dict(valid, expected_job_sha256=None),
            dict(valid, target="/private/export/forged.patch"),
            dict(valid, source_manifest_sha256="f"*64),
            dict(valid, source_patch_sha256="f"*64),
            dict(valid, action="stage", target=None),
            dict(valid, action="export-patch", target="/private/patch.patch",
                 source_manifest_sha256=None, source_patch_sha256=None),
        )
        for i, item in enumerate(bad):
            with self.subTest(index=i), self.assertRaises(
                (cli.NativeSourceDeliveryCLIHold, ValueError),
            ):
                cli.parse_delivery_request(json.dumps(item).encode())

    def test_invalid_json_duplicate_nonfinite_and_oversize_not_accepted(self):
        bad = (
            b"{}", b"[]", b"\xff",
            b'{"schema":"a","schema":"b"}',
            b'{"schema":NaN}',
            b"x"*(cli.MAX_REQUEST_BYTES+1),
        )
        for value in bad:
            with self.subTest(value=value[:20]), self.assertRaises(
                cli.NativeSourceDeliveryCLIHold,
            ):
                cli.parse_delivery_request(value)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Real source/escrow delivery needs POSIX/WSL2 custody",
)
class VerifiedNativePrivateDeliveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jeeves-native-escrow-delivery-")
        self.addCleanup(tmp.cleanup)
        self.top = Path(tmp.name)
        self.root = self.top / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "src").mkdir(mode=0o700)
        self.file = self.root / "src/app.py"
        self.original = "def start():\n    return 1\n"
        self.file.write_text(self.original, encoding="utf-8")
        self.old_sha = sha256(self.original.encode()).hexdigest()
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self.saved_path = self.private / "original.source.json"
        self.stage_path = self.private / "stage-review"
        self.patch_path = self.private / "manually-review.patch"

        def test_root(value):
            return os.open(
                value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )

        for module in (workspace, edits, patch):
            p = mock.patch.object(module, "_open_root", side_effect=test_root)
            p.start()
            self.addCleanup(p.stop)
        for module in (custody, delivery, export, overlay):
            p = mock.patch.object(
                module, "_pinned_private_directory",
                side_effect=lambda path: test_root(path.parent),
            )
            p.start()
            self.addCleanup(p.stop)

        original_proposal = mixed_source(self.old_sha)
        _, plan = mixed.review_mixed_work(original_proposal, str(self.root))
        self.proposal = original_proposal
        self.original_plan = plan
        self.model_result = {
            "schema": "jeeves.desktop.headless-native-source-receipt.v1",
            "action": "generate",
            "status": "review-required",
            "job_sha256": JOB,
            "source_context_sha256": None,
            "native_model_sha256": MODEL,
            "durable_session_id": SESSION,
            "native_source": {
                "status": "review-required",
                "model_sha256": MODEL,
                "session_id": SESSION,
                "source_manifest_sha256": plan.manifest_sha256,
                "source_patch_sha256": plan.patch_sha256,
                "operator_source_context_sha256": None,
                "attempt_count": 1,
            },
            "source_receipt_verified": True,
            "operator_patch_review_required": True,
            "private_proposal_emitted": True,
            "private_proposal": original_proposal,
            "source_files_modified": False,
            "git_commands_executed": False,
            "model_granted_filesystem_tools": False,
            "device_qualified": False,
            "release_certified": False,
        }
        self.saved = custody.publish_private_proposal(
            self.model_result, self.root, self.saved_path,
            expected_job_sha256=JOB, approve_private_storage=True,
        )

    def inspect(self):
        return delivery.inspect_saved_native_source(
            self.saved_path, project_root=str(self.root),
            expected_job_sha256=JOB,
            expected_file_sha256=self.saved["private_file_sha256"],
            expected_file_bytes=self.saved["private_file_bytes"],
        )

    def request(self, *, action="review", target=None,
                manifest=None, patch_sha=None):
        return delivery_req(
            root=self.root, escrow=self.saved_path,
            escrow_sha=self.saved["private_file_sha256"],
            escrow_bytes=self.saved["private_file_bytes"],
            action=action, target=target,
            manifest=manifest, patch_sha=patch_sha,
        )

    def test_cold_original_source_is_rechecked_without_native_inference(self):
        with (
            mock.patch("subprocess.Popen") as new_native,
            mock.patch("subprocess.run") as shell,
        ):
            inspected = self.inspect()
            report = inspected.public_review()
        self.assertEqual(report["status"],
                         "cold-saved-native-source-reviewed-not-applied")
        self.assertEqual(report["source_file_count"], 2)
        self.assertEqual(report["new_file_count"], 1)
        self.assertEqual(report["existing_edit_count"], 1)
        self.assertEqual(report["source_patch_sha256"], self.saved["source_patch_sha256"])
        self.assertEqual(report["source_manifest_sha256"],
                         self.saved["source_manifest_sha256"])
        self.assertEqual(report["original_native_model_sha256"], MODEL)
        self.assertFalse(report["additional_native_inference_executed"])
        self.assertFalse(report["source_contents_in_stdout"])
        self.assertFalse(report["original_project_modified"])
        self.assertFalse(report["git_commands_executed"])
        self.assertFalse(report["release_certified"])
        self.assertNotIn("def helper", repr(report))
        self.assertNotIn(self.original, repr(report))
        self.assertNotIn(str(self.root), repr(report))
        self.assertEqual(self.file.read_text(), self.original)
        self.assertFalse((self.root / "src/helper.py").exists())
        new_native.assert_not_called()
        shell.assert_not_called()

    def test_one_saved_native_work_can_stage_both_new_and_existing_source_privately(self):
        viewed = self.inspect()
        report = delivery.deliver_saved_native_source(
            viewed, self.stage_path, action="stage",
            expected_manifest_sha256=viewed.source_manifest_sha256,
            expected_patch_sha256=viewed.patch_sha256,
            approve_private_stage=True,
        )
        self.assertEqual(report["status"], "new-private-source-stage-completed")
        self.assertEqual(report["publication"]["file_count"], 2)
        self.assertEqual(report["source_patch_sha256"], self.saved["source_patch_sha256"])
        self.assertFalse(report["additional_model_inference_executed"])
        self.assertFalse(report["original_project_modified"])
        self.assertFalse(report["source_code_executed"])
        self.assertFalse(report["git_commands_executed"])
        self.assertEqual(self.file.read_text(), self.original)
        self.assertFalse((self.root / "src/helper.py").exists())
        self.assertTrue((self.stage_path / "seal.json").exists())
        self.assertEqual(
            (self.stage_path / "changes/src/app.py").read_text(),
            "from .helper import helper\ndef start():\n    return helper()\n",
        )
        self.assertEqual(
            (self.stage_path / "changes/src/helper.py").read_text(),
            "def helper():\n    return 42\n",
        )
        self.assertEqual(
            (self.stage_path / "changes/src/helper.py").stat().st_mode & 0o777,
            0o600,
        )

    def test_one_saved_native_work_can_export_only_inert_git_patch(self):
        viewed = self.inspect()
        receipt = delivery.deliver_saved_native_source(
            viewed, self.patch_path, action="export-patch",
            expected_manifest_sha256=viewed.source_manifest_sha256,
            expected_patch_sha256=viewed.patch_sha256,
            approve_private_patch=True,
        )
        self.assertEqual(receipt["status"], "new-private-source-patch-completed")
        self.assertEqual(receipt["publication"]["patch_sha256"],
                         self.saved["source_patch_sha256"])
        self.assertFalse(receipt["publication"]["patch_applied"])
        self.assertFalse(receipt["source_code_executed"])
        self.assertTrue(self.patch_path.is_file())
        self.assertEqual(
            sha256(self.patch_path.read_bytes()).hexdigest(),
            self.saved["source_patch_sha256"],
        )
        self.assertFalse((self.root / "src/helper.py").exists())
        self.assertEqual(self.file.read_text(), self.original)

    def test_cli_review_remains_readonly_and_private(self):
        result = cli.execute_delivery_request(self.request())
        self.assertEqual(result["status"], "reviewed-cold-source-no-private-write")
        self.assertEqual(result["review"]["source_file_count"], 2)
        self.assertIsNone(result["delivery"])
        self.assertFalse(result["native_inference_executed"])
        self.assertFalse(result["original_project_modified"])
        self.assertFalse(result["generated_source_in_stdout"])
        self.assertNotIn("def helper", repr(result))
        self.assertNotIn(str(self.root), repr(result))
        self.assertFalse(self.stage_path.exists())

    def test_cli_stage_requires_both_exact_hashes_and_distinct_approval(self):
        approved = self.request(
            action="stage", target=self.stage_path,
            manifest=self.saved["source_manifest_sha256"],
            patch_sha=self.saved["source_patch_sha256"],
        )
        with self.assertRaises(cli.NativeSourceDeliveryCLIHold):
            cli.execute_delivery_request(approved)
        with self.assertRaises(cli.NativeSourceDeliveryCLIHold):
            cli.execute_delivery_request(
                dict(approved, source_patch_sha256="f"*64),
                approve_private_stage=True,
            )
        self.assertFalse(self.stage_path.exists())
        staged = cli.execute_delivery_request(
            approved, approve_private_stage=True,
        )
        self.assertEqual(staged["delivery"]["action"], "stage")
        self.assertTrue(self.stage_path.exists())
        self.assertTrue((self.stage_path / "seal.json").exists())
        self.assertFalse(staged["generated_source_in_stdout"])

    def test_cli_patch_requires_own_flag_and_rejects_mixed_grants(self):
        requested = self.request(
            action="export-patch", target=self.patch_path,
            manifest=self.saved["source_manifest_sha256"],
            patch_sha=self.saved["source_patch_sha256"],
        )
        with self.assertRaises(cli.NativeSourceDeliveryCLIHold):
            cli.execute_delivery_request(requested, approve_private_stage=True)
        with self.assertRaises(delivery.NativeSourceDeliveryHold):
            delivery.deliver_saved_native_source(
                self.inspect(), self.patch_path, action="export-patch",
                expected_manifest_sha256=self.saved["source_manifest_sha256"],
                expected_patch_sha256=self.saved["source_patch_sha256"],
                approve_private_stage=True, approve_private_patch=True,
            )
        self.assertFalse(self.patch_path.exists())
        generated = cli.execute_delivery_request(
            requested, approve_private_patch=True,
        )
        self.assertEqual(generated["delivery"]["action"], "export-patch")
        self.assertTrue(self.patch_path.exists())

    def test_unchanged_escrow_but_modified_original_existing_source_holds(self):
        self.file.write_text(
            "def start():\n    return 99\n", encoding="utf-8",
        )
        with self.assertRaises((delivery.NativeSourceDeliveryHold, ValueError)):
            self.inspect()
        self.assertFalse(self.stage_path.exists())
        self.assertEqual(self.file.read_text(),
                         "def start():\n    return 99\n")

    def test_new_file_collision_or_changed_inode_blocks_delivery(self):
        (self.root / "src/helper.py").write_text("taken", encoding="utf-8")
        with self.assertRaises((ValueError, delivery.NativeSourceDeliveryHold)):
            self.inspect()
        self.assertFalse(self.stage_path.exists())
        self.assertEqual(
            (self.root / "src/helper.py").read_text(), "taken",
        )

    def test_escrow_tampering_and_foreign_job_sha_block_read(self):
        self.saved_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(delivery.NativeSourceDeliveryHold):
            self.inspect()
        self.assertFalse(self.stage_path.exists())

    def test_private_path_cold_read_rejects_hardlinks_and_symlinks(self):
        alias = self.private / "second.source.json"
        os.link(self.saved_path, alias)
        with self.assertRaises(delivery.NativeSourceDeliveryHold):
            self.inspect()
        alias.unlink()
        self.saved_path.unlink()
        self.saved_path.symlink_to(self.file)
        with self.assertRaises((OSError, delivery.NativeSourceDeliveryHold)):
            self.inspect()
        self.assertEqual(self.file.read_text(), self.original)

    def test_invalid_human_output_approval_does_not_touch_original(self):
        reviewed = self.inspect()
        for action, flags in (
            ("stage", (False, False)),
            ("stage", (True, True)),
            ("export-patch", (False, False)),
            ("export-patch", (True, True)),
        ):
            with self.subTest(action=action, flags=flags), self.assertRaises(
                delivery.NativeSourceDeliveryHold,
            ):
                delivery.deliver_saved_native_source(
                    reviewed, self.stage_path if action == "stage" else self.patch_path,
                    action=action,
                    expected_manifest_sha256=self.saved["source_manifest_sha256"],
                    expected_patch_sha256=self.saved["source_patch_sha256"],
                    approve_private_stage=flags[0],
                    approve_private_patch=flags[1],
                )
        self.assertFalse(self.stage_path.exists())
        self.assertFalse(self.patch_path.exists())
        self.assertEqual(self.file.read_text(), self.original)

    def test_actually_reading_headless_json_stdout_never_exposes_code(self):
        req = self.request()
        out = StringIO()
        errors = StringIO()
        with (
            mock.patch("subprocess.Popen") as native,
            mock.patch("subprocess.run") as shell,
        ):
            code = cli.main(
                [], source=BytesIO(json.dumps(req).encode()),
                output=out, errors=errors,
            )
        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        public = json.loads(out.getvalue())
        self.assertEqual(public["schema"], cli.RESULT_SCHEMA)
        self.assertEqual(public["review"]["source_file_count"], 2)
        self.assertFalse(public["native_inference_executed"])
        self.assertNotIn("def helper", out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        native.assert_not_called()
        shell.assert_not_called()

    def test_stdin_cli_missing_write_flag_is_generic_no_private_result(self):
        req = self.request(
            action="stage", target=self.stage_path,
            manifest=self.saved["source_manifest_sha256"],
            patch_sha=self.saved["source_patch_sha256"],
        )
        out = StringIO()
        err = StringIO()
        code = cli.main(
            [], source=BytesIO(json.dumps(req).encode()),
            output=out, errors=err,
        )
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("held", err.getvalue())
        self.assertNotIn(str(self.root), err.getvalue())
        self.assertFalse(self.stage_path.exists())


if __name__ == "__main__":
    unittest.main()
