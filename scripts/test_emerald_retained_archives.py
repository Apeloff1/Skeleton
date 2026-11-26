"""Focused offline fixtures; never substitute for recovered original assets."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from qualify_emerald_retained_archives import inspect_native, qualify, REQUIRED, MODEL, PREFIX


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class RetainedArchiveTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.source = self.root / "emerald-atelier-fold-source.zip"
        self.web = self.root / "emerald-skeleton-web-assets.zip"
        self.model = self.root / "emerald_continuum.glb"
        self.model_bytes = b"synthetic-model-not-a-real-glb"
        self.native_pin = {"modelBytes": len(self.model_bytes),
                           "modelSha256": hashlib.sha256(self.model_bytes).hexdigest()}

    def native(self, omit=None, extra=(), manifest_update=None):
        manifest = {"sha256": self.native_pin["modelSha256"],
                    "file_size": self.native_pin["modelBytes"],
                    "animations": 380, "joints": 108}
        manifest.update(manifest_update or {})
        with zipfile.ZipFile(self.source, "w") as archive:
            for name in sorted(REQUIRED - {omit}):
                data = json.dumps(manifest).encode() if name == "Models/manifest.json" else b"fixture"
                archive.writestr(PREFIX + name, data)
            for name, data in extra:
                archive.writestr(name, data)
        self.native_pin.update(sourceBytes=self.source.stat().st_size, sourceSha256=digest(self.source))
        return self.native_pin

    def web_pin(self):
        payload = b"synthetic"
        manifest = json.dumps({"schema": 1, "assetSet": "fixture", "scripts": [],
            "files": [{"path": "image.png", "bytes": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest()}]}).encode()
        with zipfile.ZipFile(self.web, "w") as archive:
            archive.writestr("manifest.integration.json", manifest)
            archive.writestr("image.png", payload)
        return {"bytes": self.web.stat().st_size, "sha256": digest(self.web),
                "manifestSha256": hashlib.sha256(manifest).hexdigest(), "entries": 1}

    def test_native_inventory_has_independent_hashes(self):
        result = inspect_native(self.source, self.native())
        self.assertEqual(result["entries"], len(REQUIRED))
        self.assertFalse(result["standalone_model_in_source_archive"])
        self.assertTrue(all(len(row["sha256"]) == 64 for row in result["inventory"]))

    def test_missing_required_member(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            inspect_native(self.source, self.native(omit="Art/normal.png"))

    def test_manifest_identity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "model pin mismatch"):
            inspect_native(self.source, self.native(manifest_update={"file_size": 1}))

    def test_model_must_remain_separate(self):
        with self.assertRaisesRegex(ValueError, "unexpected standalone"):
            inspect_native(self.source, self.native(extra=[(PREFIX + MODEL, b"fixture")]))

    def test_case_collision(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inspect_native(self.source, self.native(extra=[(PREFIX + "art/normal.PNG", b"fixture")]))

    def test_file_obstructs_directory(self):
        with self.assertRaisesRegex(ValueError, "obstructs"):
            inspect_native(self.source, self.native(extra=[(PREFIX + "Art", b"file")]))

    def test_wrong_archive_bytes(self):
        pin = self.native()
        with self.source.open("ab") as output:
            output.write(b"x")
        with self.assertRaises(ValueError):
            inspect_native(self.source, pin)

    def test_partial_custody_is_not_native_qualification(self):
        pin = {"assetSet": "fixture", "native": self.native(), "web": self.web_pin()}
        receipt = qualify(self.root, pin)
        self.assertTrue(receipt["web_archive_qualified"])
        self.assertTrue(receipt["native_source_archive_qualified"])
        self.assertFalse(receipt["standalone_model_bytes_verified"])
        self.assertFalse(receipt["native_staging_qualified"])
        self.assertFalse(receipt["release_qualified"])
        self.model.write_bytes(self.model_bytes)
        receipt = qualify(self.root, pin)
        self.assertTrue(receipt["standalone_model_bytes_verified"])
        self.assertFalse(receipt["native_staging_qualified"])
        self.assertFalse(receipt["engine_compiled"])


if __name__ == "__main__":
    unittest.main()
