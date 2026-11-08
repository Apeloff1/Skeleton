"""Deterministic source-bound HTML export custody regressions."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose
from skeleton.jeeves.worlds.export_verification import verify_export


class ExportVerificationTests(unittest.TestCase):
    def setUp(self):
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            self.skipTest("descriptor anchored filesystem required")
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = WorldStore(self.tmp.name)
        self.world = propose(world_id="first", premise="Cross the valley",
                             protagonist="Ari", region="Valley", goal="Reach home")
        self.digest = self.store.publish(self.world, create=True)
        self.export = self.store.compile("first", self.digest)
        self.path = Path(self.tmp.name) / "first.html"

    def test_exact_compiler_artifact_verified(self):
        result = verify_export(self.store, "first", self.digest)
        self.assertEqual(result["html_sha256"], self.export["html_sha256"])
        self.assertEqual(result["status"], "verified")

    def test_tampered_html_rejected(self):
        self.path.write_bytes(self.path.read_bytes() + b"<!-- modified -->")
        with self.assertRaisesRegex(CanonError, "export_mismatch"):
            verify_export(self.store, "first", self.digest)

    def test_missing_export_rejected(self):
        self.path.unlink()
        with self.assertRaisesRegex(CanonError, "export_not_found"):
            verify_export(self.store, "first", self.digest)

    def test_stale_revision_rejected(self):
        with self.assertRaisesRegex(CanonError, "stale_source"):
            verify_export(self.store, "first", "0" * 64)

    def test_invalid_digest_type_rejected(self):
        for invalid in (None, True, 1, "abc", "G" * 64):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(CanonError, "invalid_source_digest"):
                    verify_export(self.store, "first", invalid)

    def test_symlink_export_rejected(self):
        self.path.unlink()
        self.path.symlink_to(Path(self.tmp.name) / "missing")
        with self.assertRaises((CanonError, OSError)):
            verify_export(self.store, "first", self.digest)

    def test_hardlink_export_rejected(self):
        other = Path(self.tmp.name) / "second.html"
        os.link(self.path, other)
        with self.assertRaisesRegex(CanonError, "unsafe_export"):
            verify_export(self.store, "first", self.digest)


if __name__ == "__main__":
    unittest.main()
