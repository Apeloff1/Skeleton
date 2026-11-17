"""Offline synthetic boundary tests; actual reconstructed asset measured separately."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import rebuild_emerald_exact_binary as recovery


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.zip = self.root / "input.zip"
        self.stage = self.root / "workspace"
        self.stage.mkdir()

    def archive(self, items):
        with zipfile.ZipFile(self.zip, "w") as z:
            for name, data in items:
                z.writestr(name, data)

    def test_prefixed_members(self):
        self.archive([("source/a.txt", b"a"), ("source/deep/b.txt", b"b")])
        recovery.safe_extract(self.zip, self.stage, "source")
        self.assertEqual((self.stage / "source/deep/b.txt").read_bytes(), b"b")

    def test_unprefixed_members(self):
        self.archive([("data.txt", b"c")])
        recovery.safe_extract(self.zip, self.stage, "source")
        self.assertEqual((self.stage / "source/data.txt").read_bytes(), b"c")

    def test_no_traversal(self):
        self.archive([("../escape.txt", b"x")])
        with self.assertRaises(ValueError):
            recovery.safe_extract(self.zip, self.stage, "source")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_case_collision(self):
        self.archive([("a.txt", b"x"), ("A.TXT", b"y")])
        with self.assertRaises(ValueError):
            recovery.safe_extract(self.zip, self.stage, "source")

    def test_member_limit(self):
        self.archive([("a.txt", b"too long")])
        with patch.object(recovery, "MAX_MEMBER", 1), self.assertRaises(ValueError):
            recovery.safe_extract(self.zip, self.stage, "source")

    def test_pin_is_immutable(self):
        with self.assertRaises(ValueError):
            recovery.check_pin({"modelBytes": 1, "modelSha256": "0" * 64})

    def assemble_fixture(self, corruption=False, existing=False):
        blobs = [b"first", b"second"]
        parts = tuple((f"part{i}", len(b), sha(b)) for i, b in enumerate(blobs))
        whole = b"".join(blobs)
        for (name, _, _), data in zip(parts, blobs):
            (self.root / name).write_bytes(data)
        if corruption:
            (self.root / "part1").write_bytes(b"broken")
        target = self.root / "result.glb"
        if existing:
            target.write_bytes(b"retain")
        pin = {"modelBytes": len(whole), "modelSha256": sha(whole)}
        with patch.object(recovery, "check_pin"):
            if corruption or existing:
                with self.assertRaises((ValueError, FileExistsError)):
                    recovery.assemble(self.root, target, pin, parts)
                self.assertEqual(target.exists(), existing)
                if existing:
                    self.assertEqual(target.read_bytes(), b"retain")
            else:
                recovery.assemble(self.root, target, pin, parts)
                self.assertEqual(target.read_bytes(), whole)

    def test_exact_join(self):
        self.assemble_fixture()

    def test_bad_part_no_publication(self):
        self.assemble_fixture(corruption=True)

    def test_no_overwrite(self):
        self.assemble_fixture(existing=True)


if __name__ == "__main__":
    unittest.main()
