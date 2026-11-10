"""Offline source-bound HTML export qualification; no device or release certification."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose
from skeleton.jeeves.worlds.export_verification import verify_export


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
    "requires descriptor-relative POSIX custody",
)
class ExportCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = WorldStore(self.temp.name)
        self.source = propose(
            world_id="portable_game", premise="Retrieve the lantern",
            protagonist="Aster", region="The marsh", goal="Light the tower",
        )
        self.digest = self.store.publish(self.source, create=True)

    def test_exact_compiled_artifact_is_verified_but_not_release_approved(self):
        build = self.store.compile("portable_game", self.digest)
        receipt = verify_export(self.store, "portable_game", self.digest)
        self.assertEqual(receipt["source_digest"], self.digest)
        self.assertEqual(receipt["html_sha256"], build["html_sha256"])
        self.assertEqual(receipt["schema"], "jeeves.world.export_verification.v1")
        self.assertEqual(receipt["status"], "verified")
        self.assertNotIn("release_ready", receipt)
        self.assertNotIn("device_qualified", receipt)

    def test_missing_uncompiled_export_is_denied(self):
        with self.assertRaises(CanonError) as err:
            verify_export(self.store, "portable_game", self.digest)
        self.assertEqual(err.exception.code, "export_not_found")

    def test_stale_and_invalid_source_digests_are_denied(self):
        self.store.compile("portable_game", self.digest)
        for bad in ("0" * 64, "A" * 64, "broken", None, True):
            with self.subTest(bad=bad), self.assertRaises(CanonError):
                verify_export(self.store, "portable_game", bad)

    def test_single_byte_tamper_and_symlink_are_denied(self):
        self.store.compile("portable_game", self.digest)
        artifact = Path(self.temp.name) / "portable_game.html"
        data = artifact.read_bytes()
        artifact.write_bytes(data + b"x")
        with self.assertRaises(CanonError) as err:
            verify_export(self.store, "portable_game", self.digest)
        self.assertEqual(err.exception.code, "export_mismatch")
        artifact.unlink()
        backing = Path(self.temp.name) / "backing.html"
        backing.write_bytes(data)
        artifact.symlink_to(backing)
        with self.assertRaises((CanonError, OSError)):
            verify_export(self.store, "portable_game", self.digest)

    def test_export_must_be_nonhardlinked_regular_file(self):
        self.store.compile("portable_game", self.digest)
        artifact = Path(self.temp.name) / "portable_game.html"
        linked = Path(self.temp.name) / "other.html"
        os.link(artifact, linked)
        with self.assertRaises(CanonError) as err:
            verify_export(self.store, "portable_game", self.digest)
        self.assertEqual(err.exception.code, "unsafe_export")


if __name__ == "__main__":
    unittest.main()
