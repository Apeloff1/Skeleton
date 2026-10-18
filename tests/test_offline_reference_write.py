"""Approved local reference writes do not land before the bound approval."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.app.offline_reference_write import (
    TOOL_ID, LocalReferenceWrite, ReferenceWriteConflict, ReferenceWriteDenied,
    ReferenceWriteRejected,
)


class LocalReferenceWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = OfflineChatStore(Path(self.temp.name) / "refs.sqlite3")
        self.addCleanup(self.store.close)
        self.library = OfflineKnowledgeLibrary(self.store, "c" * 64, "d" * 64)
        self.writer = LocalReferenceWrite(self.library)
        self.writes = []
        original = self.library.add_text

        def counted(title, content):
            self.writes.append(title)
            return original(title, content)

        self.library.add_text = counted

    def test_missing_and_wrong_approval_do_not_write(self):
        request_id = str(uuid4())
        with self.assertRaises(ReferenceWriteDenied):
            self.writer.write("Notes", "The depth buffer stores pixels.", request_id, approved=False)
        with self.assertRaises(ReferenceWriteRejected):
            self.writer.write("Notes", "The depth buffer stores pixels.", request_id, approved="true")
        waiting = self.writer.write(
            "Notes", "The depth buffer stores pixels.", request_id, approved=True,
        )
        self.assertEqual(waiting["status"], "denied")
        self.assertEqual(waiting["error_code"], "approval_required")
        self.assertFalse(waiting["written"])
        self.assertTrue(waiting["expected_approval_ref"].startswith("approval:"))
        mismatched = self.writer.write(
            "Notes", "The depth buffer stores pixels.", request_id, approved=True,
            approval_ref="approval:" + ("0" * 64),
        )
        self.assertEqual(mismatched["error_code"], "approval_binding_mismatch")
        self.assertFalse(mismatched["written"])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.library.search("depth buffer"), [])

    def test_bound_approval_creates_a_searchable_document_and_rollback_removes_it(self):
        request_id = str(uuid4())
        text = "The depth buffer stores a depth value for each pixel."
        waiting = self.writer.write("GPU notes", text, request_id, approved=True)
        written = self.writer.write(
            "GPU notes", text, request_id, approved=True,
            approval_ref=waiting["expected_approval_ref"],
        )
        self.assertEqual(written["tool_id"], TOOL_ID)
        self.assertEqual(written["status"], "succeeded")
        self.assertTrue(written["created"])
        self.assertFalse(written["replayed"])
        self.assertTrue(self.library.search("depth buffer"))
        replay = self.writer.write(
            "GPU notes", text, request_id, approved=True,
            approval_ref=waiting["expected_approval_ref"],
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["receipt_id"], written["receipt_id"])
        self.assertEqual(self.writes, ["GPU notes"])
        with self.assertRaises(ReferenceWriteConflict):
            self.writer.write(
                "GPU notes", "A different stencil note for the same request.",
                request_id, approved=True, approval_ref=waiting["expected_approval_ref"],
            )
        rolled = self.writer.rollback(request_id, approved=True)
        self.assertTrue(rolled["rolled_back"])
        self.assertEqual(rolled["document_id"], written["document_id"])
        self.assertEqual(self.library.search("depth buffer"), [])
        with self.assertRaises(ReferenceWriteRejected):
            self.writer.rollback(request_id, approved=True)

    def test_reused_document_cannot_be_deleted_by_the_second_receipt(self):
        text = "The depth buffer stores a depth value for each pixel."
        first = str(uuid4())
        waiting = self.writer.write("GPU notes", text, first, approved=True)
        created = self.writer.write(
            "GPU notes", text, first, approved=True,
            approval_ref=waiting["expected_approval_ref"],
        )
        second = str(uuid4())
        again = self.writer.write("GPU notes", text, second, approved=True)
        reused = self.writer.write(
            "GPU notes", text, second, approved=True,
            approval_ref=again["expected_approval_ref"],
        )
        self.assertFalse(reused["created"])
        with self.assertRaises(ReferenceWriteRejected):
            self.writer.rollback(second, approved=True)
        self.assertTrue(self.library.search("depth buffer"))
        self.writer.rollback(first, approved=True)
        self.assertEqual(self.library.search("depth buffer"), [])
        self.assertTrue(created["created"])

    def test_unsafe_titles_do_not_write(self):
        for title in (
            "../etc/passwd",
            "/etc/passwd",
            "notes | rm -rf",
            "https://example.invalid/secret",
            "Ignore previous instructions",
        ):
            with self.subTest(title=title):
                with self.assertRaises(ReferenceWriteRejected):
                    self.writer.write(
                        title, "The depth buffer stores pixels.", str(uuid4()), approved=True,
                    )
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
