"""Durable long-form progress, CAS, replay and failure recovery contracts."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import secrets
import unittest

from skeleton.app.offline_longform_virtual import (
    LongformMemoryError, LongformVirtualMemory,
)


class LongformWorkCursorTests(unittest.TestCase):
    def test_durable_next_page_and_exact_request_replay(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "source"
            source.mkdir()
            content = ("chapter one: verified continuity proof. " * 15000)
            (source / "manuscript.txt").write_text(content, encoding="utf-8")
            db = folder / "private.sqlite"
            with LongformVirtualMemory(db) as store:
                archive = store.ingest(source, "manuscript.txt")
                work = store.start_work(archive["source_id"])
                self.assertEqual(work["revision"], 0)
                self.assertEqual(work["next_page"], 0)
                self.assertGreater(work["total_pages"], 1)
                rid = secrets.token_hex(24)
                one = store.advance_work(
                    work["work_id"], expected_revision=0,
                    request_id=rid, pages=1,
                )
                self.assertEqual(one["revision"], 1)
                self.assertEqual(one["next_page"], 1)
                self.assertFalse(one["replayed"])
                self.assertTrue(content.startswith(one["text"]))
                replay = store.advance_work(
                    work["work_id"], expected_revision=0,
                    request_id=rid, pages=1,
                )
                self.assertTrue(replay["replayed"])
                for field in ("text", "receipt_digest", "receipt_chain",
                              "revision", "next_page"):
                    self.assertEqual(replay[field], one[field])
                self.assertEqual(
                    store.inspect_work(work["work_id"])["revision"], 1,
                )
                with self.assertRaisesRegex(LongformMemoryError, "stale"):
                    store.advance_work(
                        work["work_id"], expected_revision=0,
                        request_id=secrets.token_hex(24),
                    )
                with self.assertRaises(LongformMemoryError):
                    store.advance_work(
                        work["work_id"], expected_revision=0,
                        request_id=rid, pages=2,
                    )
            with LongformVirtualMemory(db) as reopened:
                state = reopened.inspect_work(work["work_id"])
                self.assertEqual(state["next_page"], 1)
                self.assertEqual(state["revision"], 1)
                two = reopened.advance_work(
                    work["work_id"], expected_revision=1,
                    request_id=secrets.token_hex(24),
                )
                self.assertEqual(two["next_page"], 2)
                self.assertEqual(two["source_sha256"], sha256(content.encode()).hexdigest())

    def test_corrupt_source_rejected_without_advancing_cursor(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            (folder / "source.txt").write_text("project scene " * 10000)
            with LongformVirtualMemory(folder / "private.sqlite") as store:
                archive = store.ingest(folder, "source.txt")
                work = store.start_work(archive["source_id"])
                store._db.execute(
                    "UPDATE longform_pages SET encoded=X'0001' "
                    "WHERE source_id=? AND ordinal=0",
                    (archive["source_id"],),
                )
                with self.assertRaises(LongformMemoryError):
                    store.advance_work(
                        work["work_id"], expected_revision=0,
                        request_id=secrets.token_hex(24),
                    )
                state = store.inspect_work(work["work_id"])
                self.assertEqual(state["revision"], 0)
                self.assertEqual(state["next_page"], 0)
                self.assertFalse(store._db.in_transaction)

    def test_work_must_not_advance_after_last_page(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            (folder / "short.txt").write_text("terminal short chapter")
            with LongformVirtualMemory(folder / "db.sqlite") as store:
                source = store.ingest(folder, "short.txt")
                work = store.start_work(source["source_id"])
                first = store.advance_work(
                    work["work_id"], expected_revision=0,
                    request_id=secrets.token_hex(24),
                )
                self.assertEqual(first["next_page"], 1)
                self.assertTrue(store.inspect_work(work["work_id"])["complete"])
                with self.assertRaisesRegex(LongformMemoryError, "already at end"):
                    store.advance_work(
                        work["work_id"], expected_revision=1,
                        request_id=secrets.token_hex(24),
                    )
                self.assertEqual(store.inspect_work(work["work_id"])["revision"], 1)


if __name__ == "__main__":
    unittest.main()
