"""GGUF custody: no simulated activation, full hash, restart and fail-closed inputs."""
import hashlib
import os
import struct
from pathlib import Path
import tempfile
import unittest

from skeleton.local_ai.model_loader import ModelLoader


class ModelLoaderCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "model.gguf"
        self.data = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"sample-model-bytes"
        self.path.write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def qualify(self, loader=None, **overrides):
        args = {"expected_sha256": self.sha, "license_accepted": True}
        args.update(overrides)
        return (loader or ModelLoader(str(self.path))).load("c" * 32, **args)

    def test_full_digest_never_claims_inference(self):
        loader = ModelLoader(str(self.path))
        self.assertEqual(self.qualify(loader)["status"], "artifact_verified_not_loaded")
        self.assertFalse(loader.loaded)
        self.assertFalse(loader.verify(self.sha))
        self.assertEqual(self.qualify(ModelLoader(str(self.path)))["digest"], self.sha)

    def test_missing_artifact_does_not_simulate(self):
        with self.assertRaises(FileNotFoundError):
            self.qualify(ModelLoader(str(self.path) + ".missing"))

    def test_license_and_digest_required(self):
        for args, error in [
            ({"license_accepted": False}, PermissionError),
            ({"expected_sha256": None}, ValueError),
            ({"expected_sha256": "0" * 64}, ValueError),
            ({"expected_sha256": True}, ValueError),
            ({"max_bytes": True}, ValueError),
            ({"max_bytes": 5}, ValueError),
        ]:
            with self.subTest(args=args), self.assertRaises(error):
                self.qualify(**args)

    def test_invalid_format_and_truncated_hash_rejected(self):
        self.path.write_bytes(b"NOPE" + self.data[4:])
        with self.assertRaises(ValueError):
            self.qualify(expected_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.path.write_bytes(self.data + b"modified-after-first-kilobyte")
        with self.assertRaises(ValueError):
            self.qualify()

    def test_reject_magic_only_and_invalid_header(self):
        cases = [
            b"GGUF",
            b"GGUF" + struct.pack("<IQQ", 1, 1, 1),
            b"GGUF" + struct.pack("<IQQ", 3, 0, 1),
            b"GGUF" + struct.pack("<IQQ", 3, 1, 0),
            b"GGUF" + struct.pack("<IQQ", 3, 999999, 1),
        ]
        for data in cases:
            with self.subTest(data=data):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    self.qualify(expected_sha256=hashlib.sha256(data).hexdigest())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires no-follow descriptors")
    def test_symlink_and_hardlink_denied(self):
        link = self.path.with_suffix(".link")
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            self.qualify(ModelLoader(str(link)))
        link.unlink()
        os.link(self.path, link)
        with self.assertRaises(ValueError):
            self.qualify()
