"""Adversarial local source-delivery tests; operator approval is mandatory.

These tests exercise finite content and descriptor/no-replace publication in a
synthetic temporary workspace, not a real licensed GGUF or GitHub merge.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_workspace as deliver


def proposal(*files):
    return json.dumps({
        "schema": deliver.SCHEMA,
        "files": [{"path": name, "content": text} for name, text in files],
    }, separators=(",", ":"), ensure_ascii=False)


class NoOverwriteWorkspaceTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("explicit POSIX descriptor publication only")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # The separate canonical trusted-root module already verifies every
        # ancestor. These tests narrow their scope to the actual delivery
        # operation and its anchored source/target directory descriptors.
        actual_open = os.open
        patcher = mock.patch.object(
            deliver, "_open_root",
            side_effect=lambda root: actual_open(
                root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_review_then_exact_atomic_new_source_publication(self):
        sub = self.root / "src"
        sub.mkdir(mode=0o700)
        src = "def jeeves():\r\n    return 'blåbær 🌲'\r\n"
        plan = deliver.parse_plan(
            proposal(("src/jeeves.py", src)),
            self.root,
        )
        preview = deliver.preview_file(plan, 0)
        self.assertEqual(preview["sha256"], plan.entries[0].sha256)
        self.assertIn("def jeeves()", preview["diff"])
        with self.assertRaises(deliver.WorkspaceDeliveryHold):
            deliver.publish_file(
                plan, 0, expected_manifest_sha256=plan.manifest_sha256,
                expected_file_sha256=plan.entries[0].sha256, approved=False,
            )
        receipt = deliver.publish_file(
            plan, 0, expected_manifest_sha256=plan.manifest_sha256,
            expected_file_sha256=plan.entries[0].sha256, approved=True,
        )
        self.assertEqual(receipt["path"], "src/jeeves.py")
        self.assertEqual((sub / "jeeves.py").read_bytes(), src.encode("utf-8"))
        self.assertFalse(receipt["release_certified"])
        self.assertFalse(receipt["native_model_performed_file_write"])
        self.assertEqual((sub / "jeeves.py").stat().st_mode & 0o077, 0)

    def test_existing_target_is_never_overwritten_or_truncated(self):
        original = self.root / "existing.py"
        original.write_text("ORIGINAL", encoding="utf-8")
        raw = proposal(("existing.py", "NEW SOURCE"))
        with self.assertRaises(deliver.WorkspaceDeliveryHold):
            deliver.parse_plan(raw, self.root)
        self.assertEqual(original.read_text(), "ORIGINAL")

    def test_target_appearing_after_review_refuses_no_replace(self):
        plan = deliver.parse_plan(
            proposal(("future.py", "print(123)\n")), self.root,
        )
        target = self.root / "future.py"
        target.write_text("external writer", encoding="utf-8")
        with self.assertRaises(deliver.WorkspaceDeliveryHold):
            deliver.publish_file(
                plan, 0, approved=True,
                expected_manifest_sha256=plan.manifest_sha256,
                expected_file_sha256=plan.entries[0].sha256,
            )
        self.assertEqual(target.read_text(), "external writer")

    def test_staging_disk_error_cleans_random_temporary_file(self):
        plan = deliver.parse_plan(
            proposal(("future.py", "print(123)\n")), self.root,
        )
        with mock.patch.object(
            deliver.os, "write", side_effect=OSError("synthetic full disk"),
        ):
            with self.assertRaises(OSError):
                deliver.publish_file(
                    plan, 0, approved=True,
                    expected_manifest_sha256=plan.manifest_sha256,
                    expected_file_sha256=plan.entries[0].sha256,
                )
        self.assertFalse((self.root / "future.py").exists())
        self.assertFalse(any(
            name.startswith(".jeeves-stage-") for name in os.listdir(self.root)
        ))

    def test_symlinked_intermediate_parent_refused(self):
        source_dir = self.root / "dir"
        source_dir.mkdir(mode=0o700)
        (self.root / "alias").symlink_to(source_dir, target_is_directory=True)
        with self.assertRaises((deliver.WorkspaceDeliveryHold, OSError)):
            deliver.parse_plan(
                proposal(("alias/secret.py", "x=1\n")), self.root,
            )
        self.assertFalse((source_dir / "secret.py").exists())

    def test_manifest_digest_and_file_digest_are_both_required(self):
        plan = deliver.parse_plan(
            proposal(("new.py", "print('safe')\n")), self.root,
        )
        for manifest, digest in (
            ("f" * 64, plan.entries[0].sha256),
            (plan.manifest_sha256, "f" * 64),
        ):
            with self.subTest(manifest=manifest), self.assertRaises(
                deliver.WorkspaceDeliveryHold,
            ):
                deliver.publish_file(
                    plan, 0, approved=True,
                    expected_manifest_sha256=manifest,
                    expected_file_sha256=digest,
                )
        self.assertFalse((self.root / "new.py").exists())

    def test_mutated_plan_cannot_gain_authority(self):
        plan = deliver.parse_plan(
            proposal(("new.py", "print('safe')\n")), self.root,
        )
        with self.assertRaises(deliver.WorkspaceDeliveryHold):
            replace(plan, manifest_sha256="0" * 64)
        with self.assertRaises(deliver.WorkspaceDeliveryHold):
            replace(plan, root_inode=0)

    def test_all_files_have_separate_operator_approval(self):
        plan = deliver.parse_plan(
            proposal(("a.py", "a=1\n"), ("b.py", "b=2\n")), self.root,
        )
        deliver.publish_file(
            plan, 0, approved=True,
            expected_manifest_sha256=plan.manifest_sha256,
            expected_file_sha256=plan.entries[0].sha256,
        )
        self.assertTrue((self.root / "a.py").is_file())
        self.assertFalse((self.root / "b.py").exists())
        deliver.publish_file(
            plan, 1, approved=True,
            expected_manifest_sha256=plan.manifest_sha256,
            expected_file_sha256=plan.entries[1].sha256,
        )
        self.assertEqual((self.root / "b.py").read_text(), "b=2\n")

    def test_duplicate_ambiguous_unicode_and_active_workflow_denied(self):
        bads = (
            '{"schema":"jeeves.workspace.new-files.v1","files":[],"files":[]}',
            proposal(("a.py", "x"), ("A.PY", "y")),
            proposal(("../escape.py", "x")),
            proposal(("/root/out.py", "x")),
            proposal((".git/config.json", "{}")),
            proposal((".github/workflows/malware.yml", "on: push")),
            proposal((".github/SECURITY.md", "model instruction")),
            proposal((".vscode/settings.json", "{}")),
            proposal(("file.exe", "MZ")),
            proposal(("a.py", "bad\x00text")),
            proposal(("a.py", "x" * 99001)),
        )
        for value in bads:
            with self.subTest(raw=value[:60]), self.assertRaises(
                deliver.WorkspaceDeliveryHold,
            ):
                deliver.parse_plan(value, self.root)

    def test_source_proposal_never_runs_model_or_external_tools(self):
        manifest = proposal(("a.py", "import os\nprint('only text')\n"))
        with (
            mock.patch("subprocess.run") as subprocess_call,
            mock.patch("subprocess.Popen") as popen,
        ):
            plan = deliver.parse_plan(manifest, self.root)
            deliver.preview_file(plan, 0)
            subprocess_call.assert_not_called()
            popen.assert_not_called()
            self.assertFalse((self.root / "a.py").exists())


if __name__ == "__main__":
    unittest.main()
