"""Exact-source and artifact-custody tests for offline world export verification."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.worlds.export_verification import MAX_EXPORT_BYTES, verify_export
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose


class ExportVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = WorldStore(self.root)
        self.world_id = "verified"
        world = propose(
            world_id=self.world_id,
            premise="An original luminous coastline.",
            protagonist="Mira",
            region="Silver Tides",
            goal="Return the lighthouse signal",
        )
        self.digest = self.store.publish(world, create=True)

    def _export_path(self) -> Path:
        return self.root / (self.world_id + ".html")

    def test_genuine_compiled_export_proves_exact_bytes(self):
        compiled = self.store.compile(self.world_id, self.digest)
        receipt = verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["source_digest"], self.digest)
        self.assertEqual(receipt["html_sha256"], compiled["html_sha256"])
        self.assertEqual(receipt["world_id"], self.world_id)

    def test_missing_export_fails_closed(self):
        with self.assertRaises(CanonError) as caught:
            verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(caught.exception.code, "export_not_found")

    def test_stale_and_malformed_source_digest_refused(self):
        self.store.compile(self.world_id, self.digest)
        for bad in ("", "Z" * 64, "A" * 64, None):
            with self.subTest(digest=bad), self.assertRaises(CanonError):
                verify_export(self.store, self.world_id, bad)
        with self.assertRaises(CanonError) as caught:
            verify_export(self.store, self.world_id, "0" * 64)
        self.assertEqual(caught.exception.code, "stale_source")

    def test_mutated_export_cannot_be_attested(self):
        self.store.compile(self.world_id, self.digest)
        self._export_path().write_bytes(b"not the approved compiled HTML")
        with self.assertRaises(CanonError) as caught:
            verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(caught.exception.code, "export_mismatch")

    def test_oversized_export_cannot_be_read(self):
        self.store.compile(self.world_id, self.digest)
        self._export_path().write_bytes(b"X" * (MAX_EXPORT_BYTES + 1))
        with self.assertRaises(CanonError) as caught:
            verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(caught.exception.code, "unsafe_export")

    def test_extra_hardlink_cannot_be_attested(self):
        self.store.compile(self.world_id, self.digest)
        other_name = self.root / "other.html"
        os.link(self._export_path(), other_name)
        with self.assertRaises(CanonError) as caught:
            verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(caught.exception.code, "unsafe_export")

    def test_symlink_export_never_reads_foreign_target(self):
        self.store.compile(self.world_id, self.digest)
        target = self.root / "private-secret.txt"
        target.write_text("private information", encoding="utf-8")
        self._export_path().unlink()
        self._export_path().symlink_to(target)
        with self.assertRaises((CanonError, OSError)):
            verify_export(self.store, self.world_id, self.digest)
        self.assertEqual(target.read_text(encoding="utf-8"), "private information")


if __name__ == "__main__":
    unittest.main()
