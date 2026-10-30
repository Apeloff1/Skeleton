"""Merkle proof integration: selective verification scales with requested pages."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest

from skeleton.app.offline_longform_merkle import (
    EMPTY_ROOT, MerkleIntegrityError, build_merkle_tree,
    install_merkle_schema, verify_merkle_page,
)
from skeleton.app.offline_longform_virtual import (
    LongformMemoryError, LongformVirtualMemory,
)


class MerklePageProofTests(unittest.TestCase):
    def test_streaming_binary_tree_odd_nodes_and_empty_root(self):
        db = sqlite3.connect(":memory:")
        try:
            db.execute("""CREATE TABLE longform_sources (
                source_id TEXT PRIMARY KEY
            )""")
            db.execute("""CREATE TABLE longform_pages (
                source_id TEXT, ordinal INTEGER, digest TEXT,
                plain_bytes INTEGER
            )""")
            install_merkle_schema(db)
            self.assertEqual(build_merkle_tree(db, "empty", 0), EMPTY_ROOT)
            from hashlib import sha256
            source_id = "a" * 48
            for index in range(7):
                body = ("page-" + str(index)).encode()
                db.execute("INSERT INTO longform_pages VALUES (?,?,?,?)",
                           (source_id, index, sha256(body).hexdigest(), len(body)))
            root = build_merkle_tree(db, source_id, 7)
            self.assertEqual(len(root), 64)
            for index in range(7):
                body = ("page-" + str(index)).encode()
                verify_merkle_page(
                    db, source_id, ordinal=index, page_count=7,
                    byte_length=len(body), page_digest=sha256(body).hexdigest(),
                    root=root,
                )
            with self.assertRaises(MerkleIntegrityError):
                verify_merkle_page(
                    db, source_id, ordinal=6, page_count=7,
                    byte_length=6, page_digest=sha256(b"tamper").hexdigest(),
                    root=root,
                )
            db.execute(
                "UPDATE longform_merkle SET digest=? "
                "WHERE source_id=? AND level=0 AND ordinal=1",
                ("0" * 64, source_id),
            )
            with self.assertRaises(MerkleIntegrityError):
                verify_merkle_page(
                    db, source_id, ordinal=0, page_count=7,
                    byte_length=6, page_digest=sha256(b"page-0").hexdigest(),
                    root=root,
                )
        finally:
            db.close()

    def test_selected_window_does_not_scan_full_archive(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = ("Chapter continuity apple green tree. " * 40000)
            (root / "book.txt").write_text(data, encoding="utf-8")
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                receipt = store.ingest(root, "book.txt")
                self.assertGreater(receipt["page_count"], 10)
                merkle = store._db.execute(
                    "SELECT merkle_root FROM longform_sources WHERE source_id=?",
                    (receipt["source_id"],),
                ).fetchone()[0]
                self.assertEqual(len(merkle), 64)
                self.assertTrue(store.verify(receipt["source_id"])["verified"])
                # An optional complete audit is separate from the O(log N)
                # selective read. This demonstrates no hidden full-scan call.
                with patch.object(
                    store, "_read_verified",
                    side_effect=AssertionError("unexpected full archive scan"),
                ):
                    result = store.read_window(
                        receipt["source_id"], start_page=5, pages=2,
                    )
                self.assertEqual(result["verification_scope"],
                                 "selected_merkle_pages")
                self.assertEqual(result["returned_pages"], 2)
                self.assertIn("Chapter continuity", result["text"])
                with patch.object(
                    store, "_read_verified",
                    side_effect=AssertionError("unexpected full archive scan"),
                ):
                    found = store.search(
                        receipt["source_id"], "continuity", limit=1,
                    )
                self.assertTrue(found["hits"])
                self.assertFalse(found["search_completeness_proven"])
                self.assertEqual(found["verification_scope"],
                                 "selected_merkle_pages")

    def test_modified_page_and_provenance_must_fail(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work.txt").write_text("verified reference " * 15000)
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                source = store.ingest(root, "work.txt")["source_id"]
                store._db.execute(
                    "UPDATE longform_pages SET encoded=X'010203' "
                    "WHERE source_id=? AND ordinal=0",
                    (source,),
                )
                with self.assertRaises(LongformMemoryError):
                    store.read_window(source, pages=1)
            with LongformVirtualMemory(root / "vm.sqlite") as reopened:
                with self.assertRaises(LongformMemoryError):
                    reopened.verify(source)

    def test_legacy_archive_falls_back_to_full_hash_chain(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "legacy.txt").write_text("historical file " * 2000)
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                source = store.ingest(root, "legacy.txt")["source_id"]
                store._db.execute(
                    "UPDATE longform_sources SET merkle_root=NULL "
                    "WHERE source_id=?", (source,),
                )
                with patch.object(store, "_read_verified",
                                  wraps=store._read_verified) as scan:
                    result = store.read_window(source, pages=1)
                self.assertTrue(result["verified"])
                self.assertGreater(scan.call_count, 0)

    def test_end_of_work_is_not_a_missing_merkle_page(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tiny.txt").write_text("one final page")
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                source = store.ingest(root, "tiny.txt")["source_id"]
                result = store.read_window(source, start_page=1, pages=1)
                self.assertEqual(result["returned_pages"], 0)
                self.assertEqual(result["text"], "")


if __name__ == "__main__":
    unittest.main()
