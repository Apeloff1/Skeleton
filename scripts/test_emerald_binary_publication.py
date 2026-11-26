"""Publication control and byte-custody tests; no real remote operations."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import publish_emerald_binary_drafts as pub


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = (pub.ROOT / pub.MANIFEST).read_bytes()
        self.pin = json.loads((pub.ROOT / pub.PIN).read_bytes())
        self.m, self.groups = pub.manifest(self.raw, self.pin)

    def test_measured_complete_manifest(self):
        self.assertEqual(sum(g["bytes"] for g in self.m["groups"]), 706132984)
        self.assertEqual(sum(g["chunks"] for g in self.m["groups"]), 22)
        self.assertTrue(all(r["bytes"] <= 33554432 for rows in self.groups.values() for r in rows))

    def test_reject_reordered_offsets(self):
        m = copy.deepcopy(self.m)
        m["assets"][2]["chunks"][1]["offset"] = 0
        with self.assertRaisesRegex(ValueError, "chunk contract"):
            pub.manifest(json.dumps(m).encode(), self.pin)

    def test_reject_repin(self):
        m = copy.deepcopy(self.m)
        m["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "asset pin mismatch"):
            pub.manifest(json.dumps(m).encode(), self.pin)

    def fixture(self, data=b"original"):
        row = {"path": "assets/test.part001", "bytes": len(data), "sha256": pub.digest(data)}
        return row, data

    def bundle(self, *, payload=b"original", extra=False, manifest=None):
        row, data = self.fixture()
        path = self.root / "bundle.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("publication-manifest.json", self.raw if manifest is None else manifest)
            z.writestr(row["path"], payload)
            if extra:
                z.writestr("foreign.txt", b"x")
        return path, row, data

    def test_bundle_exact(self):
        path, row, data = self.bundle()
        self.assertEqual(list(pub.bundle_rows(path, [row], self.raw)), [(row, data)])

    def test_bundle_rejects_same_length_corruption(self):
        path, row, _ = self.bundle(payload=b"modified")
        with self.assertRaisesRegex(ValueError, "chunk identity"):
            list(pub.bundle_rows(path, [row], self.raw))

    def test_bundle_rejects_extra(self):
        path, row, _ = self.bundle(extra=True)
        with self.assertRaisesRegex(ValueError, "inventory"):
            list(pub.bundle_rows(path, [row], self.raw))

    def test_bundle_rejects_wrong_manifest(self):
        path, row, _ = self.bundle(manifest=b"wrong")
        with self.assertRaisesRegex(ValueError, "manifest mismatch"):
            list(pub.bundle_rows(path, [row], self.raw))

    def test_whole_asset_must_match(self):
        row, data = self.fixture()
        m = {"assets": [{"name": "whole.bin", "bytes": len(data),
                         "sha256": "0" * 64, "chunks": [row]}]}
        target = self.root / "out"
        with self.assertRaisesRegex(ValueError, "whole asset pin mismatch"):
            pub.write_originals(m, target, lambda _: data)
        self.assertFalse(target.exists())

    def test_exact_atomic_restore(self):
        row, data = self.fixture()
        m = {"assets": [{"name": "whole.bin", "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest(), "chunks": [row]}]}
        target = self.root / "out"
        pub.write_originals(m, target, lambda _: data)
        self.assertEqual((target / "whole.bin").read_bytes(), data)
        with self.assertRaisesRegex(ValueError, "exists"):
            pub.write_originals(m, target, lambda _: data)

    def test_wrong_push_url_rejected(self):
        with patch.object(pub, "git", side_effect=[
            b"https://github.com/Apeloff1/Skeleton.git\n", b"https://example.invalid/repo.git\n"
        ]), self.assertRaisesRegex(ValueError, "authorized"):
            pub.check_remote(self.root)


if __name__ == "__main__":
    unittest.main()
