"""Real Git-format tests for human-reviewed offline Jeeves source patches.

All original project and output paths are ephemeral fixtures. The fake root
descriptor allows /tmp in source-only tests; production still requires the
canonical nofollow trusted-root chain. Git is used here ONLY to validate and
apply generated patch bytes inside disposable TEST checkouts after the product
implementation, never by production Jeeves or against the user's repository.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_patch_bundle as patch,
    desktop_patch_export as export,
    desktop_existing_edits as edits,
    desktop_workspace as workspace,
)


def _new(*entries):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": path, "content": text} for path, text in entries],
    }, ensure_ascii=False)


def _edit(*entries):
    return json.dumps({
        "schema": edits.SCHEMA,
        "files": [
            {
                "path": path,
                "expected_sha256": sha256(original.encode("utf-8")).hexdigest(),
                "replacement": replacement,
            } for path, original, replacement in entries
        ],
    }, ensure_ascii=False)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Descriptor-rooted source work requires POSIX/WSL2",
)
class GitPatchReviewTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="jeeves-git-review-")
        self.addCleanup(self._temporary.cleanup)
        self.top = Path(self._temporary.name)
        self.root = self.top / "project"
        self.root.mkdir(mode=0o700)
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self._patchers = []

        def open_test_root(value):
            return os.open(
                value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )

        # CI temp workspaces may live beneath the world-writable /tmp.
        # Only these test-only source-root openers relax ancestry checks.
        # Product code retains its original descriptor custody.
        for module in (workspace, edits, patch):
            opened = mock.patch.object(
                module, "_open_root", side_effect=open_test_root,
            )
            opened.start()
            self.addCleanup(opened.stop)
        self.git = shutil.which("git")

    def make_file(self, name, data):
        source = self.root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data.encode("utf-8", "strict"))
        return source

    def plan(self, *, new=None, changed=None):
        return patch.review_patch_bundle(
            self.root, new_files=new, existing_edits=changed,
        )

    def private_path(self):
        return self.private / "approved-native-change.patch"

    def export(self, plan, *, path=None, approval=True):
        return export.export_reviewed_patch(
            plan, path or self.private_path(),
            expected_manifest_sha256=plan.manifest_sha256,
            expected_patch_sha256=plan.patch_sha256,
            approve_export=approval,
        )

    def _git_apply(self, data, *, check_only):
        if self.git is None:
            self.skipTest("Git CLI not installed on isolated test runner")
        proposal = self.top / "verify-git.patch"
        proposal.write_bytes(data)
        if not (self.root / ".git").exists():
            subprocess.run(
                [self.git, "-C", str(self.root), "init", "-q"],
                check=True, capture_output=True, timeout=20,
            )
        args = [
            self.git, "-C", str(self.root), "apply",
        ] + (["--check"] if check_only else []) + [
            str(proposal),
        ]
        return subprocess.run(
            args, capture_output=True, text=True,
            check=False, timeout=20,
        )

    def test_mixed_new_and_existing_changes_render_valid_git_diff(self):
        original = "def message():\n    return 'før'\n"
        replacement = "def message():\n    return 'etter'\n"
        source = self.make_file("pkg/core.py", original)
        plan = self.plan(
            new=_new(
                ("pkg/extra.py", "answer = 42\n"),
                ("README.md", "# Offline Jeeves\n"),
            ),
            changed=_edit(("pkg/core.py", original, replacement)),
        )
        self.assertEqual(len(plan.entries), 3)
        self.assertEqual(plan.public_review()["new_files"], 2)
        self.assertEqual(plan.public_review()["existing_edits"], 1)
        self.assertEqual(
            list(e.path for e in plan.entries),
            ["pkg/core.py", "pkg/extra.py", "README.md"],
        )
        original_bytes = source.read_bytes()
        rendered = patch.get_reviewed_patch(plan)
        self.assertEqual(sha256(rendered).hexdigest(), plan.patch_sha256)
        self.assertIn(b"diff --git a/pkg/core.py b/pkg/core.py", rendered)
        self.assertIn(b"new file mode 100644", rendered)
        self.assertIn("etter".encode("utf-8"), rendered)
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertFalse((self.root / "pkg" / "extra.py").exists())
        self.assertEqual(self._git_apply(rendered, check_only=True).returncode, 0)
        self.assertEqual(source.read_bytes(), original_bytes)
        # ONLY source-only test fixture gets to execute an explicit Git apply.
        self.assertEqual(self._git_apply(rendered, check_only=False).returncode, 0)
        self.assertEqual(source.read_text(), replacement)
        self.assertEqual((self.root / "pkg" / "extra.py").read_text(), "answer = 42\n")

    def test_missing_eof_newline_is_roundtripped_exactly(self):
        old, changed = "alpha=1", "alpha=2"
        source = self.make_file("bare.py", old)
        plan = self.plan(
            changed=_edit(("bare.py", old, changed)),
            new=_new(("fresh.txt", "no newline here")),
        )
        raw = patch.get_reviewed_patch(plan)
        self.assertIn(b"\\ No newline at end of file\n", raw)
        self.assertEqual(self._git_apply(raw, check_only=True).returncode, 0)
        self.assertEqual(self._git_apply(raw, check_only=False).returncode, 0)
        self.assertEqual(source.read_bytes(), b"alpha=2")
        self.assertEqual((self.root / "fresh.txt").read_bytes(), b"no newline here")

    def test_crlf_and_unicode_are_source_bytes_not_automatic_normalization(self):
        old = "one\r\ntwo\r\n"
        new = "one\r\ntwo 🌳\r\n"
        source = self.make_file("view.txt", old)
        plan = self.plan(changed=_edit(("view.txt", old, new)))
        raw = patch.get_reviewed_patch(plan)
        self.assertIn("two 🌳".encode("utf-8"), raw)
        self.assertEqual(self._git_apply(raw, check_only=True).returncode, 0)
        self.assertEqual(self._git_apply(raw, check_only=False).returncode, 0)
        self.assertEqual(source.read_bytes(), new.encode("utf-8"))

    def test_unicode_line_separator_is_not_a_real_git_newline(self):
        old = "before\u2028after\n"
        new = "before\u2028updated\n"
        source = self.make_file("unicode.py", old)
        plan = self.plan(changed=_edit(("unicode.py", old, new)))
        raw = patch.get_reviewed_patch(plan)
        self.assertEqual(self._git_apply(raw, check_only=True).returncode, 0)
        self.assertEqual(self._git_apply(raw, check_only=False).returncode, 0)
        self.assertEqual(source.read_bytes(), new.encode("utf-8"))

    def test_reordered_new_sources_have_same_manifest_and_patch_bytes(self):
        entries = (("z.py", "z=9\n"), ("a.py", "a=1\n"))
        a = self.plan(new=_new(*entries))
        b = self.plan(new=_new(*reversed(entries)))
        self.assertEqual(a.manifest_sha256, b.manifest_sha256)
        self.assertEqual(a.patch_sha256, b.patch_sha256)
        self.assertEqual(
            patch.get_reviewed_patch(a), patch.get_reviewed_patch(b),
        )

    def test_existing_original_drift_refuses_patch_export(self):
        old, new = "mode=1\n", "mode=2\n"
        original = self.make_file("owner.py", old)
        planned = self.plan(changed=_edit(("owner.py", old, new)))
        original.write_text("mode=999\n", encoding="utf-8")
        with self.assertRaises(patch.PatchBundleHold):
            patch.get_reviewed_patch(planned)
        with self.assertRaises(export.PatchExportHold):
            self.export(planned)
        self.assertFalse(self.private_path().exists())
        self.assertEqual(original.read_text(), "mode=999\n")

    def test_changed_inode_same_content_after_review_is_held(self):
        original = self.make_file("original.py", "x=1\n")
        plan = self.plan(changed=_edit(("original.py", "x=1\n", "x=2\n")))
        replacement = self.make_file("replacement.py", "x=1\n")
        os.replace(replacement, original)
        with self.assertRaises(patch.PatchBundleHold):
            patch.get_reviewed_patch(plan)
        self.assertEqual(original.read_text(), "x=1\n")

    def test_symlink_leaf_after_review_is_refused(self):
        plan = self.plan(new=_new(("planned.py", "version=1\n")))
        original = self.make_file("actual.py", "original=1\n")
        (self.root / "planned.py").symlink_to(original)
        with self.assertRaises(patch.PatchBundleHold):
            patch.get_reviewed_patch(plan)
        self.assertEqual(original.read_text(), "original=1\n")

    def test_protected_metadata_path_and_shell_authority_not_exported(self):
        for name in (
            ".git/config", ".github/workflows/evil.yml",
            "../outside.py", "pkg/../../outside.py",
            "pkg/secret.py/../pass.py",
        ):
            with self.subTest(name=name), self.assertRaises(patch.PatchBundleHold):
                self.plan(new=_new((name, "enabled = True\n")))
        self.assertFalse((self.root / ".github").exists())

    def test_original_source_paths_not_in_public_review(self):
        self.make_file("hello.py", "x=1\n")
        plan = self.plan(changed=_edit(("hello.py", "x=1\n", "x=2\n")))
        public = plan.public_review()
        self.assertFalse(public["project_files_modified"])
        self.assertFalse(public["patch_applied"])
        self.assertFalse(public["native_model_authorized_to_write"])
        self.assertFalse(public["release_certified"])
        self.assertNotIn(str(self.root), repr(public))
        self.assertNotIn("x=1", repr(public))
        self.assertNotIn("x=2", repr(public))

    def test_input_control_bytes_nonfinite_and_overlarge_files_are_denied(self):
        bads = (
            _new(("foo.py", "bad\u0001source\n")),
            _new(("foo.py", "\u0000untrusted\n")),
            _new(("foo.py", "x" * 100000)),
            '{"schema":"jeeves.workspace.new-files.v1","files":[]}',
            '{"schema":"jeeves.workspace.new-files.v1","files":[{"path":"a.py","content":"x","extra":true}]}',
            _new(("same.py", "x=1\n"), ("same.py", "x=2\n")),
        )
        for raw in bads:
            with self.subTest(raw=raw[:75]), self.assertRaises(
                (patch.PatchBundleHold, ValueError),
            ):
                self.plan(new=raw)

    def test_missing_proposals_and_untrusted_source_root_denied(self):
        with self.assertRaises(patch.PatchBundleHold):
            self.plan()
        with self.assertRaises(patch.PatchBundleHold):
            patch.review_patch_bundle("../relative", new_files=_new(("x.py", "x=1")))
        with self.assertRaises(patch.PatchBundleHold):
            patch.review_patch_bundle(
                self.root, new_files=None, existing_edits="not JSON",
            )


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Owner-private patch export requires POSIX/WSL2",
)
class PrivatePatchExportTests(GitPatchReviewTests):
    def test_explicit_double_digest_and_private_consent(self):
        planned = self.plan(new=_new(("safe.py", "safe=1\n")))
        for args in (
            {"approve_export": False},
            {"approve_export": 1},
            {"expected_manifest_sha256": "f" * 64},
            {"expected_patch_sha256": "f" * 64},
            {"expected_patch_sha256": True},
        ):
            kwargs = dict(
                plan=planned, target=self.private_path(),
                expected_manifest_sha256=planned.manifest_sha256,
                expected_patch_sha256=planned.patch_sha256,
                approve_export=True,
            )
            kwargs.update(args)
            with self.subTest(args=args), self.assertRaises(export.PatchExportHold):
                export.export_reviewed_patch(**kwargs)
        self.assertFalse(self.private_path().exists())

    def test_creates_only_one_private_0600_patch_no_project_changes(self):
        self.make_file("base.py", "old=1\n")
        plan = self.plan(
            changed=_edit(("base.py", "old=1\n", "old=2\n")),
            new=_new(("additional.py", "extra=1\n")),
        )
        receipt = self.export(plan)
        output = self.private_path()
        self.assertTrue(output.is_file())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(output.stat().st_nlink, 1)
        self.assertEqual(receipt["patch_sha256"], plan.patch_sha256)
        self.assertEqual(receipt["file_count"], 2)
        self.assertFalse(receipt["project_files_modified"])
        self.assertFalse(receipt["git_index_modified"])
        self.assertFalse(receipt["patch_applied"])
        self.assertFalse(receipt["model_authorized_file_write"])
        self.assertFalse(receipt["release_certified"])
        self.assertEqual((self.root / "base.py").read_text(), "old=1\n")
        self.assertFalse((self.root / "additional.py").exists())
        exact = output.read_bytes()
        self.assertEqual(sha256(exact).hexdigest(), plan.patch_sha256)
        self.assertEqual(self._git_apply(exact, check_only=True).returncode, 0)
        independently = export.verify_saved_patch(
            output, workspace_root=self.root,
            expected_patch_sha256=plan.patch_sha256,
            expected_bytes=len(exact),
        )
        self.assertEqual(independently["patch_sha256"], plan.patch_sha256)
        self.assertFalse(independently["project_files_modified"])

    def test_private_destination_existing_file_never_overwritten(self):
        plan = self.plan(new=_new(("source.py", "src=1\n")))
        self.export(plan)
        original = self.private_path().read_bytes()
        with self.assertRaises(FileExistsError):
            self.export(plan)
        self.assertEqual(self.private_path().read_bytes(), original)

    def test_symlink_destination_never_follows_or_overwrites(self):
        planned = self.plan(new=_new(("new.py", "new=True\n")))
        foreign = self.private / "foreign.txt"
        foreign.write_text("do not replace me", encoding="utf-8")
        self.private_path().symlink_to(foreign)
        with self.assertRaises((OSError, export.PatchExportHold)):
            self.export(planned)
        self.assertEqual(foreign.read_text(), "do not replace me")

    def test_patch_export_inside_source_tree_is_refused(self):
        plan = self.plan(new=_new(("new.py", "new=True\n")))
        with self.assertRaises(export.PatchExportHold):
            self.export(plan, path=self.root / "inert.patch")
        self.assertFalse((self.root / "inert.patch").exists())

    def test_parent_directory_must_be_owner_private(self):
        plan = self.plan(new=_new(("new.py", "new=True\n")))
        os.chmod(self.private, 0o755)
        with self.assertRaises(export.PatchExportHold):
            self.export(plan)
        self.assertFalse(self.private_path().exists())

    def test_saved_patch_tamper_cannot_be_certified(self):
        plan = self.plan(new=_new(("source.py", "code=123\n")))
        self.export(plan)
        file = self.private_path()
        file.write_bytes(b"changed by another process")
        with self.assertRaises(export.PatchExportHold):
            export.verify_saved_patch(
                file, workspace_root=self.root,
                expected_patch_sha256=plan.patch_sha256,
                expected_bytes=plan.patch_bytes,
            )

    def test_saved_patch_hardlink_and_unsafe_mode_are_denied(self):
        plan = self.plan(new=_new(("source.py", "code=123\n")))
        self.export(plan)
        alias = self.private / "second.patch"
        os.link(self.private_path(), alias)
        with self.assertRaises(export.PatchExportHold):
            export.verify_saved_patch(
                alias, workspace_root=self.root,
                expected_patch_sha256=plan.patch_sha256,
                expected_bytes=plan.patch_bytes,
            )
        os.unlink(alias)
        os.chmod(self.private_path(), 0o644)
        with self.assertRaises(export.PatchExportHold):
            export.verify_saved_patch(
                self.private_path(), workspace_root=self.root,
                expected_patch_sha256=plan.patch_sha256,
                expected_bytes=plan.patch_bytes,
            )

    def test_export_name_must_be_safe_portable_patch_extension(self):
        plan = self.plan(new=_new(("source.py", "code=123\n")))
        for path in (
            self.private / "malicious.sh",
            self.private / ".hidden.patch",
            self.private / "source.patch/../escape.patch",
            self.private / "bad name.patch",
        ):
            with self.subTest(path=path), self.assertRaises(export.PatchExportHold):
                self.export(plan, path=path)


if __name__ == "__main__":
    unittest.main()
