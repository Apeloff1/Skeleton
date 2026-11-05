"""Existing-file editing is an explicit human-reviewed *candidate* workflow.

No model has a write grant. These tests use temporary original sources under
a test-only root descriptor; the production code still verifies each file,
hash, owner, mode, inode and original snapshot before it stages a distinct
new file. They do not qualify a physical GGUF, model output or consumer release.
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
    desktop_existing_edits as edit,
)


def payload(*rows):
    return json.dumps(
        {"schema": edit.SCHEMA, "files": [
            {
                "path": name, "expected_sha256": sha256(old.encode()).hexdigest(),
                "replacement": new,
            } for name, old, new in rows
        ]},
        sort_keys=True, ensure_ascii=False,
    )


class OriginalSourceCandidateTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("POSIX descriptor-anchored source editing only")
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        def open_test_root(path):
            return os.open(
                path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        patcher = mock.patch.object(
            edit, "_open_root", side_effect=open_test_root,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _source(self, path: str, text: str) -> Path:
        location = self.root / path
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes(text.encode("utf-8", "strict"))
        return location

    def _review(self, filename: str, old: str, new: str):
        original = self._source(filename, old)
        plan = edit.parse_existing_edits(
            payload((filename, old, new)), self.root,
        )
        return original, plan

    def _publish(self, plan, index=0):
        e = plan.edits[index]
        return edit.stage_existing_edit_candidate(
            plan, index,
            expected_manifest_sha256=plan.manifest_sha256,
            expected_original_sha256=e.original_sha256,
            expected_replacement_sha256=e.replacement_sha256,
            approved=True,
        )

    def test_preview_and_stage_leave_original_bytes_untouched(self):
        old = "def greet():\r\n    return 'hej 🌲'\r\n"
        new = "def greet():\r\n    return 'offline jeeves 🌲'\r\n"
        original, plan = self._review("src/hello.py", old, new)
        source_digest = sha256(old.encode()).hexdigest()
        edit_digest = sha256(new.encode()).hexdigest()
        review = edit.preview_existing_edit(plan, 0)
        self.assertIn("-    return 'hej", review["diff"])
        self.assertIn("+    return 'offline", review["diff"])
        self.assertEqual(review["original_sha256"], source_digest)
        self.assertEqual(review["replacement_sha256"], edit_digest)
        self.assertFalse(review["existing_file_modified"])
        receipt = self._publish(plan)
        self.assertEqual(receipt["status"], "candidate-atomically-created-no-original-write")
        self.assertEqual(original.read_bytes(), old.encode())
        candidate = original.parent / receipt["candidate_name"]
        self.assertTrue(candidate.is_file())
        self.assertEqual(candidate.read_bytes(), new.encode())
        self.assertEqual(candidate.stat().st_mode & 0o077, 0)
        self.assertFalse(receipt["existing_file_modified"])
        self.assertFalse(receipt["native_model_authorized_file_write"])
        self.assertFalse(receipt["release_certified"])

    def test_original_content_drift_refuses_candidate(self):
        old, new = "x=1\n", "x=2\n"
        original, plan = self._review("main.py", old, new)
        original.write_text("x=999\n", encoding="utf-8")
        with self.assertRaises(edit.ExistingEditHold):
            self._publish(plan)
        self.assertEqual(original.read_text(), "x=999\n")
        self.assertFalse(any(
            p.name.startswith(".jeeves-edit-candidate-")
            for p in self.root.iterdir()
        ))

    def test_inplace_chmod_after_review_refuses_candidate(self):
        original, plan = self._review("main.py", "x=1\n", "x=2\n")
        os.chmod(original, 0o666)
        with self.assertRaises(edit.ExistingEditHold):
            self._publish(plan)
        self.assertEqual(original.read_text(), "x=1\n")

    def test_symlinked_existing_source_refused_before_review(self):
        actual = self._source("real.py", "x=1\n")
        (self.root / "alias.py").symlink_to(actual)
        with self.assertRaises((OSError, edit.ExistingEditHold)):
            edit.parse_existing_edits(
                payload(("alias.py", "x=1\n", "x=2\n")),
                self.root,
            )
        self.assertEqual(actual.read_text(), "x=1\n")

    def test_unowned_world_writable_existing_source_refused(self):
        original = self._source("change.py", "x=1\n")
        os.chmod(original, 0o666)
        with self.assertRaises(edit.ExistingEditHold):
            edit.parse_existing_edits(
                payload(("change.py", "x=1\n", "x=2\n")),
                self.root,
            )

    def test_existing_candidate_name_is_never_overwritten(self):
        old, new = "value = 1\n", "value = 2\n"
        original, plan = self._review("state.py", old, new)
        first = self._publish(plan)
        candidate = original.parent / first["candidate_name"]
        with self.assertRaises(edit.ExistingEditHold):
            self._publish(plan)
        self.assertEqual(candidate.read_text(), new)
        self.assertEqual(original.read_text(), old)

    def test_original_hardlink_alias_is_rejected(self):
        original = self._source("real.py", "x=1\n")
        os.link(original, self.root / "alias.py")
        with self.assertRaises(edit.ExistingEditHold):
            edit.parse_existing_edits(
                payload(("real.py", "x=1\n", "x=2\n")),
                self.root,
            )

    def test_tampered_expected_hash_cannot_stage(self):
        old, new = "x=1\n", "x=2\n"
        self._source("main.py", old)
        wrong = json.dumps({
            "schema": edit.SCHEMA,
            "files": [{
                "path": "main.py", "expected_sha256": "f" * 64,
                "replacement": new,
            }],
        })
        with self.assertRaises(edit.ExistingEditHold):
            edit.parse_existing_edits(wrong, self.root)

    def test_operator_must_approve_full_manifest_original_and_new_sha(self):
        original, plan = self._review("main.py", "x=1\n", "x=2\n")
        args = dict(
            plan=plan, index=0,
            expected_manifest_sha256=plan.manifest_sha256,
            expected_original_sha256=plan.edits[0].original_sha256,
            expected_replacement_sha256=plan.edits[0].replacement_sha256,
            approved=True,
        )
        for change in (
            {"approved": False},
            {"approved": 1},
            {"expected_manifest_sha256": "f" * 64},
            {"expected_original_sha256": "f" * 64},
            {"expected_replacement_sha256": "f" * 64},
        ):
            with self.subTest(change=change), self.assertRaises(edit.ExistingEditHold):
                edit.stage_existing_edit_candidate(**{**args, **change})
        self.assertEqual(original.read_text(), "x=1\n")

    def test_second_proposed_change_needs_separate_digest_approval(self):
        self._source("first.py", "a=1\n")
        self._source("second.py", "b=1\n")
        plan = edit.parse_existing_edits(payload(
            ("first.py", "a=1\n", "a=2\n"),
            ("second.py", "b=1\n", "b=2\n"),
        ), self.root)
        self._publish(plan, 0)
        self.assertEqual((self.root / "second.py").read_text(), "b=1\n")
        self.assertEqual(
            len([p for p in self.root.iterdir()
                 if p.name.startswith(".jeeves-edit-candidate-")]),
            1,
        )
        self._publish(plan, 1)
        self.assertEqual((self.root / "second.py").read_text(), "b=1\n")

    def test_duplicate_paths_binary_and_unsafe_control_files_are_refused(self):
        old = "x=1\n"
        self._source("real.py", old)
        bad = (
            payload(("real.py", old, "x=2\n"),
                    ("real.py", old, "x=3\n")),
            payload(("real.py", old, "x=1\n")),
            payload(("real.py", old, "bad\x00text")),
            payload(("../escape.py", old, "x=2\n")),
            payload((".github/workflows/main.yml", old, "on: push")),
            '{"schema":"jeeves.workspace.existing-file-edits.v1","files":[],"files":[]}',
            '{"schema":"jeeves.workspace.existing-file-edits.v1","files":[{"path":"real.py","expected_sha256":NaN,"replacement":"a"}]}',
        )
        for proposal in bad:
            with self.subTest(proposal=proposal[:50]), self.assertRaises(
                (edit.ExistingEditHold, edit.WorkspaceDeliveryHold),
            ):
                edit.parse_existing_edits(proposal, self.root)
        self.assertEqual((self.root / "real.py").read_text(), old)

    def test_disk_failure_cleans_staging_without_mutating_original(self):
        original, plan = self._review("main.py", "x=1\n", "x=2\n")
        with mock.patch.object(
            edit.os, "write", side_effect=OSError("synthetic exhausted disk"),
        ):
            with self.assertRaises(OSError):
                self._publish(plan)
        self.assertEqual(original.read_text(), "x=1\n")
        self.assertFalse(any(
            p.name.startswith(".jeeves-stage-") for p in self.root.iterdir()
        ))

    def test_review_and_publication_have_no_external_execution(self):
        original = self._source("main.py", "x=1\n")
        with (
            mock.patch("subprocess.run") as run,
            mock.patch("subprocess.Popen") as launch,
        ):
            plan = edit.parse_existing_edits(
                payload(("main.py", "x=1\n", "x=2\n")), self.root,
            )
            edit.preview_existing_edit(plan, 0)
            self._publish(plan)
            run.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(original.read_text(), "x=1\n")


if __name__ == "__main__":
    unittest.main()
