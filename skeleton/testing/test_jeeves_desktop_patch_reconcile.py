"""Three-way merge-free safe source recovery for original Jeeves proposals.

These tests use source-only temporary file descriptors; the actual user
project, native model, Git index and original SQLite are never mutated.
Conflicting model/editor changes are always explicit holds. No model is
allowed to apply a proposed reconciliation without a fresh operator review.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_patch_reconcile as reconcile,
    desktop_patch_bundle as patch,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)


def proposal(path, original, model):
    return json.dumps({
        "schema": edits.SCHEMA,
        "files": [{
            "path": path, "expected_sha256": sha256(
                original.encode("utf-8", "strict")
            ).hexdigest(),
            "replacement": model,
        }],
    }, ensure_ascii=False)


class PureThreeWayDiffTests(unittest.TestCase):
    def test_independent_local_and_model_changes_are_combined_only_as_text(self):
        base = "first\nsecond\nthird\n"
        local = "first LOCAL\nsecond\nthird\n"
        model = "first\nsecond\nthird JEEVES\n"
        result, lh, mh, conflicts = reconcile.rebase_line_edits(
            base, local, model,
        )
        self.assertEqual(result, "first LOCAL\nsecond\nthird JEEVES\n")
        self.assertEqual((lh, mh, conflicts), (1, 1, 0))

    def test_same_line_conflict_never_takes_the_model_choice(self):
        merged, lh, mh, conflict = reconcile.rebase_line_edits(
            "count=1\n", "count=42\n", "count=9\n",
        )
        self.assertIsNone(merged)
        self.assertEqual(lh, 1)
        self.assertEqual(mh, 1)
        self.assertEqual(conflict, 1)

    def test_identical_local_and_model_change_is_already_present(self):
        base = "a\nb\nc\n"
        updated = "a\nb changed\nc\n"
        merged, lh, mh, conflicts = reconcile.rebase_line_edits(
            base, updated, updated,
        )
        self.assertEqual(merged, updated)
        self.assertEqual((lh, mh, conflicts), (1, 1, 0))

    def test_two_different_inserts_same_position_conflict(self):
        base = "base\n"
        a = "local\nbase\n"
        b = "model\nbase\n"
        merged, _, _, overlaps = reconcile.rebase_line_edits(base, a, b)
        self.assertIsNone(merged)
        self.assertGreater(overlaps, 0)

    def test_insert_at_replace_boundary_is_conservative_conflict(self):
        base = "first\nsecond\n"
        local = "first local\nsecond\n"
        model = "model insert\nfirst\nsecond\n"
        merged, _, _, overlaps = reconcile.rebase_line_edits(base, local, model)
        self.assertIsNone(merged)
        self.assertGreater(overlaps, 0)

    def test_disjoint_adjacent_lines_are_safe_independent_changes(self):
        base = "first\nsecond\nthird\n"
        local = "local\nsecond\nthird\n"
        proposed = "first\nmodel\nthird\n"
        merged, _, _, overlaps = reconcile.rebase_line_edits(
            base, local, proposed,
        )
        self.assertEqual(merged, "local\nmodel\nthird\n")
        self.assertEqual(overlaps, 0)

    def test_mixed_crlf_no_final_newline_preserved(self):
        original = "first\r\nsecond"
        local = "FIRST\r\nsecond"
        proposed = "first\r\nSECOND"
        result, _, _, overlaps = reconcile.rebase_line_edits(
            original, local, proposed,
        )
        self.assertEqual(result, "FIRST\r\nSECOND")
        self.assertEqual(overlaps, 0)

    def test_excessive_line_count_and_bad_types_are_held(self):
        with self.assertRaises(reconcile.PatchReconcileHold):
            reconcile.rebase_line_edits(
                "a\n"*2050, "b\n"*2050, "c\n"*2050,
            )
        with self.assertRaises(reconcile.PatchReconcileHold):
            reconcile.rebase_line_edits(123, "safe", "safe")


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "POSIX descriptor-rooted source reconciliation required",
)
class ActualProjectReconcileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jeeves-merge-review-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "pkg").mkdir(mode=0o700)

        def test_open_root(path):
            return os.open(
                path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        for module in (workspace, edits, patch, reconcile):
            guard = mock.patch.object(
                module, "_open_root", side_effect=test_open_root,
            )
            guard.start()
            self.addCleanup(guard.stop)

    def source(self, name, value):
        selected = self.root / name
        selected.write_text(value, encoding="utf-8")
        return selected

    def plan(self, name, original, proposed):
        self.source(name, original)
        return patch.review_patch_bundle(
            self.root, existing_edits=proposal(name, original, proposed),
        )

    def test_rebased_source_proposal_requires_fresh_original_digest(self):
        base = "a=1\nb=2\nc=3\n"
        mine = "a=10\nb=2\nc=3\n"
        proposed = "a=1\nb=2\nc=30\n"
        original_plan = self.plan("pkg/source.py", base, proposed)
        file = self.root / "pkg/source.py"
        file.write_text(mine, encoding="utf-8")
        with mock.patch("subprocess.Popen") as process:
            report = reconcile.reconcile_reviewed_patch(original_plan)
        process.assert_not_called()
        self.assertEqual(report.status, "rebased-review-required")
        self.assertEqual(report.to_public()["rebased_count"], 1)
        self.assertFalse(report.to_public()["original_source_modified"])
        self.assertFalse(report.to_public()["git_index_modified"])
        self.assertFalse(report.to_public()["automatic_conflict_resolution"])
        self.assertNotIn("a=10", repr(report.to_public()))
        self.assertEqual(file.read_text(), mine)
        rerendered = json.loads(report.existing_proposal)
        row = rerendered["files"][0]
        self.assertEqual(row["expected_sha256"], sha256(mine.encode()).hexdigest())
        self.assertEqual(row["replacement"], "a=10\nb=2\nc=30\n")
        # Operator must review the changed source again, creating a NEW
        # manifest/patch SHA-256; old approval cannot authorize the rebase.
        new_plan = patch.review_patch_bundle(
            self.root, existing_edits=report.existing_proposal,
        )
        self.assertNotEqual(
            new_plan.manifest_sha256, original_plan.manifest_sha256,
        )
        self.assertEqual(new_plan.entries[0].original_sha256,
                         sha256(mine.encode()).hexdigest())

    def test_same_line_editor_model_conflict_returns_no_partial_proposal(self):
        chosen = self.plan("pkg/source.py", "x=1\n", "x=2\n")
        file = self.root / "pkg/source.py"
        file.write_text("x=3\n", encoding="utf-8")
        report = reconcile.reconcile_reviewed_patch(chosen)
        self.assertEqual(report.status, "conflicts-held")
        self.assertEqual(report.to_public()["conflict_count"], 1)
        self.assertEqual(report.files[0].status, "conflict")
        self.assertIsNone(report.existing_proposal)
        self.assertIsNone(report.new_proposal)
        self.assertEqual(file.read_text(), "x=3\n")

    def test_if_model_change_already_applied_no_new_work_is_minted(self):
        chosen = self.plan("pkg/source.py", "x=1\n", "x=2\n")
        file = self.root / "pkg/source.py"
        file.write_text("x=2\n", encoding="utf-8")
        outcome = reconcile.reconcile_reviewed_patch(chosen)
        self.assertEqual(outcome.status, "already-present-no-work")
        self.assertEqual(outcome.to_public()["already_present_count"], 1)
        self.assertIsNone(outcome.existing_proposal)
        self.assertIsNone(outcome.new_proposal)
        self.assertEqual(file.read_text(), "x=2\n")

    def test_unchanged_original_still_needs_new_proposal_review(self):
        chosen = self.plan("pkg/source.py", "a=1\n", "a=2\n")
        report = reconcile.reconcile_reviewed_patch(chosen)
        self.assertEqual(report.status, "rebased-review-required")
        self.assertEqual(report.files[0].status, "unchanged-original")
        self.assertEqual(json.loads(report.existing_proposal)["files"][0]["replacement"], "a=2\n")
        self.assertFalse(report.to_public()["patch_applied"])

    def test_new_source_collision_blocks_the_entire_mixed_proposal(self):
        old = "a=1\nb=2\nc=3\n"
        proposed = "a=1\nb=2\nc=4\n"
        self.source("pkg/old.py", old)
        chosen = patch.review_patch_bundle(
            self.root,
            new_files=json.dumps({
                "schema": workspace.SCHEMA,
                "files": [{"path": "pkg/new.py", "content": "new=1\n"}],
            }),
            existing_edits=proposal("pkg/old.py", old, proposed),
        )
        self.source("pkg/new.py", "foreign=1\n")
        outcome = reconcile.reconcile_reviewed_patch(chosen)
        self.assertEqual(outcome.status, "conflicts-held")
        self.assertEqual(outcome.to_public()["conflict_count"], 1)
        self.assertIsNone(outcome.new_proposal)
        self.assertIsNone(outcome.existing_proposal)
        self.assertEqual((self.root / "pkg/new.py").read_text(), "foreign=1\n")

    def test_existing_source_replaced_by_symlink_is_a_hold(self):
        chosen = self.plan("pkg/old.py", "a=1\n", "a=2\n")
        file = self.root / "pkg/old.py"
        file.unlink()
        file.symlink_to(self.root / "pkg" / "target.py")
        with self.assertRaises((reconcile.PatchReconcileHold, OSError)):
            reconcile.reconcile_reviewed_patch(chosen)

    def test_project_root_inode_changed_is_not_rebound_implicitly(self):
        chosen = self.plan("pkg/old.py", "a=1\n", "a=2\n")
        old = self.root.with_name("project-old")
        os.rename(self.root, old)
        self.root.mkdir(mode=0o700)
        (self.root / "pkg").mkdir(mode=0o700)
        with self.assertRaises(reconcile.PatchReconcileHold):
            reconcile.reconcile_reviewed_patch(chosen)

    def test_reconciled_original_report_is_tamper_evident(self):
        original = self.plan(
            "pkg/old.py", "a=1\nb=2\n", "a=1\nb=3\n",
        )
        (self.root / "pkg/old.py").write_text(
            "a=2\nb=2\n", encoding="utf-8",
        )
        report = reconcile.reconcile_reviewed_patch(original)
        self.assertEqual(report.status, "rebased-review-required")
        self.assertEqual(len(report.rebase_sha256), 64)
        with self.assertRaises(reconcile.PatchReconcileHold):
            reconcile.ReconcileReport(
                original_manifest_sha256=report.original_manifest_sha256,
                original_patch_sha256=report.original_patch_sha256,
                rebase_sha256="f"*64,
                files=report.files, status=report.status,
                new_proposal=report.new_proposal,
                existing_proposal=report.existing_proposal,
            )

    def test_no_disposable_subprocess_or_original_writes_during_reconcile(self):
        old = "a=1\nb=2\nc=3\n"
        chosen = self.plan("pkg/old.py", old, "a=1\nb=2\nc=9\n")
        path = self.root / "pkg/old.py"
        path.write_text("a=2\nb=2\nc=3\n", encoding="utf-8")
        with (
            mock.patch("subprocess.run") as command,
            mock.patch("subprocess.Popen") as process,
        ):
            result = reconcile.reconcile_reviewed_patch(chosen)
        command.assert_not_called()
        process.assert_not_called()
        self.assertEqual(result.status, "rebased-review-required")
        self.assertEqual(path.read_text(), "a=2\nb=2\nc=3\n")
        self.assertNotIn("c=9", repr(result.to_public()))


if __name__ == "__main__":
    unittest.main()
