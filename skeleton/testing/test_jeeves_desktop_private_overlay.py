"""Private source overlay staging tests for the offline Jeeves workbench.

The product may place exact reviewed source bytes in a separate private
preview directory without touching the original checkout. Every test uses
throwaway files and synthetic source proposals. No production Git command,
model inference, native GGUF, or generated code execution occurs.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_private_overlay as overlay,
    desktop_patch_bundle as bundle,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)

MIB = 1024 * 1024


def new_proposal(*items):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": path, "content": content} for path, content in items],
    }, ensure_ascii=False)


def edit_proposal(*items):
    return json.dumps({
        "schema": edits.SCHEMA,
        "files": [{
            "path": path,
            "expected_sha256": sha256(original.encode("utf-8")).hexdigest(),
            "replacement": replacement,
        } for path, original, replacement in items],
    }, ensure_ascii=False)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Owner-private read-only source overlays need POSIX/WSL2 descriptors",
)
class PrivateSourceOverlayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="jeeves-overlay-source-only-")
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        self.project = self.top / "project"
        self.project.mkdir(mode=0o700)
        (self.project / "src").mkdir(mode=0o700)
        self.private = self.top / "private"
        self.private.mkdir(mode=0o700)
        self.stage = self.private / "manual-review-stage"
        self.origin = self.project / "src/app.py"
        self.old = "def main():\n    return 1\n"
        self.new = "def main():\n    return 2\n"
        self.origin.write_text(self.old, encoding="utf-8")

        def direct_test_root(value):
            return os.open(
                value,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        # The ephemeral runner's /tmp ancestors are intentionally shared;
        # patch ONLY their source-root openers, never production custody.
        for module in (workspace, edits, bundle):
            original = mock.patch.object(
                module, "_open_root", side_effect=direct_test_root,
            )
            original.start()
            self.addCleanup(original.stop)
        export_parent = mock.patch.object(
            overlay, "_pinned_private_directory",
            side_effect=lambda path: direct_test_root(path.parent),
        )
        export_parent.start()
        self.addCleanup(export_parent.stop)

    def plan(self, *, code=None, edit=None):
        if code is None:
            code = "def helper():\n    return 42\n"
        if edit is None:
            edit = self.new
        return bundle.review_patch_bundle(
            self.project,
            new_files=new_proposal(
                ("src/helper.py", code),
                ("README.md", "# Original local project\n"),
            ),
            existing_edits=edit_proposal(
                ("src/app.py", self.old, edit),
            ),
        )

    def stage_plan(self, plan=None, **override):
        plan = plan or self.plan()
        arguments = {
            "expected_manifest_sha256": plan.manifest_sha256,
            "expected_patch_sha256": plan.patch_sha256,
            "approve_staging": True,
        }
        arguments.update(override)
        return overlay.stage_reviewed_overlay(
            plan, self.stage, **arguments,
        )

    def inspect(self, plan=None, *, target=None, **changes):
        plan = plan or self.plan()
        options = {
            "expected_manifest_sha256": plan.manifest_sha256,
            "expected_patch_sha256": plan.patch_sha256,
            "workspace_root": self.project,
        }
        options.update(changes)
        return overlay.verify_staged_overlay(
            target or self.stage, **options,
        )

    def test_mixed_source_tree_staged_exactly_and_original_checkout_untouched(self):
        plan = self.plan()
        expected_old = self.origin.read_bytes()
        original_dir = set(os.listdir(self.project))
        with (
            mock.patch("subprocess.Popen") as external_process,
            mock.patch("subprocess.run") as shell,
            mock.patch("os.system") as system,
        ):
            receipt = self.stage_plan(plan)
            separately = self.inspect(plan)
            external_process.assert_not_called()
            shell.assert_not_called()
            system.assert_not_called()
        self.assertTrue(self.stage.is_dir())
        self.assertEqual(self.stage.stat().st_mode & 0o777, 0o700)
        self.assertEqual(receipt["file_count"], 3)
        self.assertEqual(receipt["source_files_staged"], 3)
        self.assertTrue(receipt["complete_marker_verified"])
        self.assertFalse(receipt["automatic_project_activation"])
        self.assertTrue(receipt["manual_operator_checkout_review_required"])
        self.assertFalse(receipt["original_checkout_modified"])
        self.assertFalse(receipt["git_index_modified"])
        self.assertFalse(receipt["model_source_write_authorized"])
        self.assertFalse(receipt["source_code_executed"])
        self.assertFalse(receipt["release_certified"])
        self.assertEqual(self.origin.read_bytes(), expected_old)
        self.assertEqual(set(os.listdir(self.project)), original_dir)
        self.assertFalse((self.project / "README.md").exists())
        self.assertFalse((self.project / "src/helper.py").exists())
        self.assertEqual(
            (self.stage / "changes/src/app.py").read_text(), self.new,
        )
        self.assertEqual(
            (self.stage / "changes/src/helper.py").read_text(),
            "def helper():\n    return 42\n",
        )
        self.assertEqual(
            (self.stage / "changes/README.md").read_text(),
            "# Original local project\n",
        )
        self.assertEqual(receipt["manifest_sha256"], plan.manifest_sha256)
        self.assertEqual(receipt["patch_sha256"], plan.patch_sha256)
        self.assertEqual(len(receipt["python_source_graph_sha256"]), 64)
        self.assertEqual(
            receipt["python_source_graph_sha256"],
            separately["python_source_graph_sha256"],
        )
        self.assertEqual(receipt["python_source_graph_status"],
                         "observed-internal-imports")
        self.assertFalse(separately["graph_reparsed_on_cold_reopen"])
        self.assertEqual(separately["status"],
                         "complete-private-source-overlay-snapshot")
        self.assertEqual(separately["file_count"], 3)
        self.assertEqual(separately["metadata_sha256"],
                         receipt["metadata_sha256"])
        for path in (
            self.stage / "changes/src/app.py",
            self.stage / "changes/src/helper.py",
            self.stage / "changes/README.md",
            self.stage / "manifest.json",
            self.stage / "seal.json",
        ):
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)

    def test_cold_reopen_verifies_without_plan_or_live_native_session(self):
        plan = self.plan()
        written = self.stage_plan(plan)
        again = overlay.verify_staged_overlay(
            self.stage,
            expected_manifest_sha256=plan.manifest_sha256,
            expected_patch_sha256=plan.patch_sha256,
            workspace_root=self.project,
        )
        self.assertEqual(again["metadata_sha256"], written["metadata_sha256"])
        self.assertFalse(again["source_code_executed"])
        self.assertFalse(again["release_certified"])

    def test_no_overwrite_existing_private_stage_directory(self):
        plan = self.plan()
        receipt = self.stage_plan(plan)
        old = (self.stage / "changes/src/app.py").read_bytes()
        with self.assertRaises(FileExistsError):
            self.stage_plan(plan)
        self.assertEqual((self.stage / "changes/src/app.py").read_bytes(), old)
        self.assertTrue(self.inspect(plan)["status"].startswith("complete-"))
        self.assertEqual(receipt["source_files_staged"], 3)

    def test_new_stage_name_must_be_canonical_and_outside_source(self):
        plan = self.plan()
        bad = (
            self.project / "inside",
            self.project / "src/inside",
            self.private / ".hidden",
            self.private / "wrong/name",
            self.private / "../outside",
            self.private / "stage.sh/" / "x",
            Path("relative-stage"),
        )
        for dest in bad:
            with self.subTest(destination=str(dest)), self.assertRaises(
                (overlay.SourceOverlayHold, ValueError, OSError),
            ):
                overlay.stage_reviewed_overlay(
                    plan, dest, approve_staging=True,
                    expected_manifest_sha256=plan.manifest_sha256,
                    expected_patch_sha256=plan.patch_sha256,
                )
        self.assertFalse(self.stage.exists())

    def test_stage_requires_both_full_digests_and_explicit_typed_consent(self):
        plan = self.plan()
        cases = (
            {"expected_manifest_sha256": "0"*64},
            {"expected_patch_sha256": "b"*64},
            {"expected_patch_sha256": True},
            {"expected_manifest_sha256": plan.manifest_sha256[:20]},
            {"approve_staging": False},
            {"approve_staging": 1},
            {"approve_staging": None},
        )
        for option in cases:
            with self.subTest(option=option), self.assertRaises(
                overlay.SourceOverlayHold,
            ):
                self.stage_plan(plan, **option)
        self.assertFalse(self.stage.exists())

    def test_invalid_python_blocks_stage_before_any_directory_creation(self):
        plan = self.plan(code="def broken(:\n")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.stage_plan(plan)
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.origin.read_text(), self.old)

    def test_changed_original_source_holds_without_creating_stage(self):
        plan = self.plan()
        self.origin.write_text("def main():\n    return 999\n", encoding="utf-8")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.stage_plan(plan)
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.origin.read_text(), "def main():\n    return 999\n")

    def test_new_path_collision_holds_without_creating_stage(self):
        plan = self.plan()
        (self.project / "src/helper.py").write_text(
            "operator new source", encoding="utf-8",
        )
        with self.assertRaises(overlay.SourceOverlayHold):
            self.stage_plan(plan)
        self.assertFalse(self.stage.exists())
        self.assertEqual(
            (self.project / "src/helper.py").read_text(),
            "operator new source",
        )

    def test_tamper_to_exact_staged_source_is_rejected_at_cold_verification(self):
        plan = self.plan()
        self.stage_plan(plan)
        file = self.stage / "changes/src/app.py"
        file.write_text(self.new.replace("2", "9"), encoding="utf-8")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)
        self.assertEqual(self.origin.read_text(), self.old)

    def test_truncated_manifest_and_altered_seal_are_rejected(self):
        plan = self.plan()
        self.stage_plan(plan)
        file = self.stage / "manifest.json"
        original = file.read_bytes()
        file.write_bytes(b"{}")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)
        file.write_bytes(original)
        seal = self.stage / "seal.json"
        seal.write_bytes(b"{}")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)

    def test_unexpected_extra_stage_file_or_directory_is_not_certified(self):
        plan = self.plan()
        self.stage_plan(plan)
        extra = self.stage / "changes/src/unapproved.py"
        extra.write_text("arbitrary extra source", encoding="utf-8")
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)
        extra.unlink()
        new_dir = self.stage / "changes/alien"
        new_dir.mkdir()
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)

    def test_stage_symlink_parent_or_source_leaf_fails(self):
        plan = self.plan()
        self.stage_plan(plan)
        source = self.stage / "changes/src/app.py"
        source.unlink()
        source.symlink_to(self.origin)
        with self.assertRaises((OSError, overlay.SourceOverlayHold)):
            self.inspect(plan)
        self.assertEqual(self.origin.read_text(), self.old)

    def test_staged_source_hardlink_and_relaxed_permissions_fail(self):
        plan = self.plan()
        self.stage_plan(plan)
        target = self.stage / "changes/README.md"
        copy = self.private / "second-hardlink.md"
        os.link(target, copy)
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)
        copy.unlink()
        os.chmod(target, 0o644)
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)

    def test_staged_directory_permissions_cannot_be_relaxed(self):
        plan = self.plan()
        self.stage_plan(plan)
        os.chmod(self.stage / "changes/src", 0o755)
        with self.assertRaises(overlay.SourceOverlayHold):
            self.inspect(plan)

    def test_original_revalidation_after_source_write_failure_never_seals(self):
        plan = self.plan()
        original_write = overlay._write_private
        count = 0
        def failing_write(fd, name, payload):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulate disk full or cancelled operation")
            return original_write(fd, name, payload)
        with mock.patch.object(
            overlay, "_write_private", side_effect=failing_write,
        ):
            with self.assertRaises(OSError):
                self.stage_plan(plan)
        self.assertTrue(self.stage.is_dir())
        self.assertFalse((self.stage / "seal.json").exists())
        with self.assertRaises((OSError, overlay.SourceOverlayHold)):
            self.inspect(plan)
        self.assertEqual(self.origin.read_text(), self.old)

    def test_unsupported_source_is_not_misrepresented_as_compiled(self):
        plan = self.plan(code="function helper() { return true; }\n")
        # Python suffix is supported, so JavaScript syntax in a .py is held.
        with self.assertRaises(overlay.SourceOverlayHold):
            self.stage_plan(plan)
        self.assertFalse(self.stage.exists())


if __name__ == "__main__":
    unittest.main()
