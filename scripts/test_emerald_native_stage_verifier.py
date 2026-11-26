import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_emerald_native_stage as verifier


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.source = self.root / "source.zip"
        self.target = self.root / "staged"
        self.target.mkdir()
        self.rows = {}
        for name, data in (("Art/normal.png", b"map"), (verifier.MODEL, b"model")):
            path = self.target / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            self.rows[name] = {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        self.pin = {"modelSha256": self.rows[verifier.MODEL]["sha256"],
                    "modelBytes": 5, "sourceSha256": "0" * 64}
        self.receipt = {"schema": 1, "files": [self.rows[k] for k in sorted(self.rows)],
                        "model_sha256": self.pin["modelSha256"], "source_sha256": self.pin["sourceSha256"],
                        "equipment_enabled": False, "engine_compiled": False,
                        "physical_rtx_verified": False, "artist_approved": False}
        self.write_receipt()
        self.addCleanup(patch.stopall)
        patch.object(verifier, "expected_inventory", return_value=self.rows).start()
        self.structure = patch.object(verifier, "verify_model").start()

    def write_receipt(self):
        (self.target / verifier.RECEIPT).write_text(json.dumps(self.receipt))

    def test_exact_stage(self):
        result = verifier.verify(self.target, self.source, self.pin)
        self.assertTrue(result["native_staging_qualified"])
        self.assertFalse(result["release_qualified"])
        self.structure.assert_called_once()

    def test_extra_file_rejected(self):
        (self.target / "extra").touch()
        with self.assertRaisesRegex(ValueError, "unexpected"):
            verifier.verify(self.target, self.source, self.pin)

    def test_corruption_rejected_even_if_receipt_changed(self):
        (self.target / "Art/normal.png").write_bytes(b"bad")
        self.receipt["files"] = [dict(row) for row in self.receipt["files"]]
        self.receipt["files"][0]["sha256"] = hashlib.sha256(b"bad").hexdigest()
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verifier.verify(self.target, self.source, self.pin)

    def test_missing_file(self):
        (self.target / "Art/normal.png").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            verifier.verify(self.target, self.source, self.pin)

    def test_receipt_cannot_qualify_rtx(self):
        self.receipt["physical_rtx_verified"] = True
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            verifier.verify(self.target, self.source, self.pin)

    def test_symlink(self):
        path = self.target / "Art/normal.png"
        path.unlink()
        try:
            path.symlink_to(self.source)
        except OSError:
            self.skipTest("symlinks not available")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            verifier.verify(self.target, self.source, self.pin)


if __name__ == "__main__":
    unittest.main()
