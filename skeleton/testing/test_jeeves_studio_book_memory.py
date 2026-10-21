"""Local full-book memory: real bytes, FTS search, rights and receipt replay."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.training.book_learning_bridge import compile_book_intake
from skeleton.jeeves.ai.studio_book_memory import ReviewedBookMemory, BookMemoryError


class BookMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.admitted = self.root / "admitted"
        self.admitted.mkdir()
        self.index = self.root / "library.sqlite"
        self.original = (
            "Original archipelago navigation choices preserve island canon, "
            "character continuity and satisfying alternative endings. "
        ) * 50
        self.engineering = (
            "Velocity, traction and turbulence create tangible responsive "
            "physics gameplay across grounded vehicle scenarios. "
        ) * 50
        books = []
        for index, (book_id, chapter, family, text) in enumerate((
            ("book-narrative", "narrative.txt", "narrative", self.original),
            ("book-mechanics", "mechanics.txt", "mechanics", self.engineering),
        )):
            raw = text.encode("utf-8")
            (self.root / chapter).write_bytes(raw)
            books.append({
                "id": book_id, "title": "Original Manual " + str(index),
                "rights": {
                    "schema_version": "skeleton.jeeves.game_corpus_rights.v1",
                    "source_kind": "original_authoring",
                    "training_permitted": True,
                    "rights_holder": "Verified Author",
                    "rights_basis": "Original manuscript cleared for training",
                    "review_id": "license-reviewed",
                },
                "chapters": [{
                    "id": "chapter-one", "file": chapter,
                    "sha256": sha256(raw).hexdigest(),
                    "family": family, "quality_approved": True,
                    "quality_reviewer_id": "human-auditor",
                    "quality_review_note": "Complete original manuscript content independently approved.",
                }],
            })
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "skeleton.jeeves.book_weights_intake.v1",
            "books": books,
        }))
        self.source_receipt = compile_book_intake(
            manifest, self.admitted, operator_review_id="operator-legal",
        )
        self.receipt_path = self.admitted / "jeeves-books-operator-legal-receipts.json"
        self.expected = sha256(self.receipt_path.read_bytes()).hexdigest()

    def build(self):
        return ReviewedBookMemory.build(
            self.index, project_id="game-one",
            admission_receipt=self.receipt_path, admitted_dir=self.admitted,
            expected_receipt_sha256=self.expected,
        )

    def open_index(self):
        memory = ReviewedBookMemory(
            self.index, project_id="game-one",
            admission_sha256=self.expected,
        )
        self.addCleanup(memory.close)
        return memory

    def test_real_full_book_source_is_indexed_without_training(self):
        proof = self.build()
        self.assertEqual(proof["indexed_segments"],
                         self.source_receipt["training_examples"])
        self.assertFalse(proof["model_weights_modified"])
        self.assertEqual(proof["admission_receipt_sha256"], self.expected)
        self.assertEqual(self.open_index().verify()["source_root_sha256"],
                         proof["source_root_sha256"])

    def test_family_scoped_search_and_source_citation(self):
        self.build()
        result = self.open_index().search(
            "What affects island navigation and endings?",
            actor_id="jeeves", family="narrative",
        )
        self.assertTrue(result["results"])
        self.assertEqual({item["book_id"] for item in result["results"]},
                         {"book-narrative"})
        self.assertTrue(all(len(item["excerpt"]) <= 480 for item in result["results"]))
        self.assertFalse(result["model_weights_modified"])
        self.assertEqual(len(result["retrieval_receipt_sha256"]), 64)

    def test_negative_search_does_not_fabricate_a_source(self):
        self.build()
        result = self.open_index().search(
            "nonexistentquantumflibble", actor_id="jeeves",
        )
        self.assertEqual(result["results"], [])
        self.assertEqual(result["results_sha256"],
                         sha256(b"[]").hexdigest())

    def test_revoke_book_excludes_all_related_chunks(self):
        self.build()
        memory = self.open_index()
        self.assertTrue(memory.search("archipelago", actor_id="jeeves")["results"])
        head = memory.revoke_book(
            "book-narrative", reviewer_id="human-auditor",
            reason="Human rights holder revoked permitted model access",
        )
        self.assertEqual(len(head), 64)
        self.assertFalse(memory.search("archipelago", actor_id="jeeves")["results"])
        with self.assertRaises(BookMemoryError):
            memory.revoke_book(
                "book-narrative", reviewer_id="human-auditor",
                reason="Human rights holder revoked permitted model access",
            )
        self.assertEqual(len(memory.search("traction", actor_id="jeeves")["results"]) > 0,
                         True)

    def test_wrong_project_and_mismatched_admission_refused(self):
        self.build()
        with self.assertRaises(BookMemoryError):
            ReviewedBookMemory(self.index, project_id="another-game",
                               admission_sha256=self.expected)
        with self.assertRaises(BookMemoryError):
            ReviewedBookMemory(self.index, project_id="game-one",
                               admission_sha256="0" * 64)

    def test_independently_pinned_receipt_must_match_source_bytes(self):
        with self.assertRaises(BookMemoryError):
            ReviewedBookMemory.build(
                self.index, project_id="game-one",
                admission_receipt=self.receipt_path, admitted_dir=self.admitted,
                expected_receipt_sha256="f" * 64,
            )
        self.assertFalse(self.index.exists())

    def test_exclusive_index_never_replaces_existing_source(self):
        self.build()
        with self.assertRaises(BookMemoryError):
            self.build()

    def test_external_source_tampering_invalidates_query(self):
        self.build()
        memory = self.open_index()
        memory.search("archipelago", actor_id="jeeves")
        with sqlite3.connect(self.index) as database:
            database.execute(
                "UPDATE segment SET text='forged novel' "
                "WHERE book_id='book-narrative'"
            )
        with self.assertRaises(BookMemoryError):
            memory.search("archipelago", actor_id="jeeves")

    def test_altered_retrieval_receipt_is_detected(self):
        self.build()
        memory = self.open_index()
        memory.search("velocity", actor_id="jeeves")
        with sqlite3.connect(self.index) as database:
            database.execute(
                "UPDATE retrieval SET result_sha=? WHERE sequence=0",
                ("a" * 64,),
            )
        with self.assertRaises(BookMemoryError):
            memory.verify()

    def test_raw_fts_operator_not_executable_as_query(self):
        self.build()
        memory = self.open_index()
        result = memory.search('archipelago" OR NOT canon:*',
                               actor_id="jeeves")
        self.assertTrue(result["results"])
        self.assertEqual(result["project_id"], "game-one")


if __name__ == "__main__":
    unittest.main()
