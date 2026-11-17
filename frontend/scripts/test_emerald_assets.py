import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("install_emerald", Path(__file__).with_name("install_emerald_assets.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / "bundle.zip"
        self.target = self.root / "target"

    def make(self, name="asset.png", payload=b"test", actual=None, extra=None):
        manifest = {"schema": 1, "assetSet": "test", "scripts": [], "files": [{"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]}
        raw = json.dumps(manifest).encode()
        with zipfile.ZipFile(self.archive, "w") as out:
            out.writestr(mod.MANIFEST, raw)
            out.writestr(name, payload if actual is None else actual)
            if extra:
                out.writestr(*extra)
        return {"assetSet": "test", "web": {"manifestSha256": hashlib.sha256(raw).hexdigest(), "bytes": self.archive.stat().st_size, "sha256": mod.digest(self.archive), "entries": 1}}

    def test_install_and_replay(self):
        pin = self.make()
        mod.install(self.archive, self.target, pin)
        mod.install(self.archive, self.target, pin)
        self.assertEqual((self.target / "asset.png").read_bytes(), b"test")

    def test_reject_traversal(self):
        pin = self.make("../escape.png")
        with self.assertRaises(ValueError):
            mod.install(self.archive, self.target, pin)
        self.assertFalse(self.target.exists())

    def test_reject_digest_mismatch(self):
        pin = self.make(actual=b"evil")
        with self.assertRaises(ValueError):
            mod.install(self.archive, self.target, pin)
        self.assertFalse(self.target.exists())

    def test_reject_extra(self):
        pin = self.make(extra=("extra.js", b"x"))
        with self.assertRaises(ValueError):
            mod.install(self.archive, self.target, pin)

    def test_extracts_only_private_verified_snapshot(self):
        pin=self.make()
        original=mod.exact_snapshot
        def mutate_after_snapshot(archive,destination,expected):
            original(archive,destination,expected)
            archive.write_bytes(b"replacement")
        with patch.object(mod,"exact_snapshot",mutate_after_snapshot):
            mod.install(self.archive,self.target,pin)
        self.assertEqual((self.target/"asset.png").read_bytes(),b"test")
        self.assertFalse(any(p.name.startswith(".emerald-stage-") for p in self.root.iterdir()))

    def test_reject_corrupt_initial_archive(self):
        pin=self.make()
        self.archive.write_bytes(b"x"*self.archive.stat().st_size)
        with self.assertRaises(ValueError):mod.install(self.archive,self.target,pin)
        self.assertFalse(self.target.exists())

    def test_installed_mutation(self):
        pin = self.make()
        mod.install(self.archive, self.target, pin)
        (self.target / "asset.png").write_bytes(b"evil")
        with self.assertRaises(ValueError):
            mod.install(self.archive, self.target, pin)

if __name__ == "__main__":
    unittest.main()
