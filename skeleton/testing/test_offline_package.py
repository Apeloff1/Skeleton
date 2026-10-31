"""Deterministic offline source archive acceptance and adversarial tests."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from skeleton.game.build.flgb_build_runtime import BuildContractError
from skeleton.game.build.offline_package import build_package, verify_package

FILES = {
    "game/story.txt": b"Original Lantern Harbor quest.\\n",
    "game/scene.json": b'{"version":1,"name":"harbor"}',
}


class OfflinePackageTests(unittest.TestCase):
    def test_deterministic_roundtrip_and_canonical_receipt(self):
        first = build_package("harbor-demo", "Skeleton original studio", "CC0-1.0", FILES)
        second = build_package("harbor-demo", "Skeleton original studio", "CC0-1.0", dict(reversed(list(FILES.items()))))
        self.assertEqual(first, second)
        receipt = verify_package(first)
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["unsigned"])
        self.assertFalse(receipt["release_certified"])
        self.assertEqual(receipt["files"], 2)
        with zipfile.ZipFile(BytesIO(first)) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json", "game/scene.json", "game/story.txt"])
            self.assertEqual(archive.read("game/story.txt"), FILES["game/story.txt"])

    def test_reject_traversal_reserved_and_budget(self):
        for path in ("../secret", "/absolute", "dir/../secret", "a\\\\b", "manifest.json", "dir//x", "a/./b", ".git/config", "payload.sh", ".github/workflows/evil.yml"):
            with self.subTest(path=path), self.assertRaises(BuildContractError):
                build_package("test", "Skeleton original studio", "CC0-1.0", {path: b"x"})
        with self.assertRaises(BuildContractError):
            build_package("test", "Skeleton original studio", "CC0-1.0", {"a.txt": b"x" * 1048577})
        with self.assertRaises(BuildContractError):
            build_package("test", "Skeleton original studio", "unknown", FILES)
        with self.assertRaises(BuildContractError):
            build_package("test", "Skeleton original studio", "CC0-1.0", {})

    def test_tampered_manifest_and_payload_rejected(self):
        original = build_package("harbor-demo", "Skeleton original studio", "CC0-1.0", FILES)
        with zipfile.ZipFile(BytesIO(original)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        manifest["entries"][0]["sha256"] = "0" * 64
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in (("manifest.json", json.dumps(manifest).encode()),
                                  ("game/scene.json", FILES["game/scene.json"]),
                                  ("game/story.txt", FILES["game/story.txt"])):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        with self.assertRaises(BuildContractError):
            verify_package(output.getvalue())

    def test_reject_trailing_bytes_and_noncanonical_metadata(self):
        original = build_package("harbor-demo", "Skeleton original studio", "CC0-1.0", FILES)
        with self.assertRaises(BuildContractError):
            verify_package(original + b"untrusted-trailer")

    def test_reject_zip_slip_symlink_and_compression(self):
        for name, mode, compression in (
            ("../escape", 0o100644, zipfile.ZIP_STORED),
            ("bad-link", 0o120777, zipfile.ZIP_STORED),
            ("bad-deflate", 0o100644, zipfile.ZIP_DEFLATED),
        ):
            original = build_package("harbor-demo", "Skeleton original studio", "CC0-1.0", FILES)
            with zipfile.ZipFile(BytesIO(original)) as archive:
                manifest = archive.read("manifest.json")
            output = BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                info = zipfile.ZipInfo("manifest.json")
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, manifest)
                bad = zipfile.ZipInfo(name)
                bad.create_system = 3
                bad.external_attr = mode << 16
                bad.compress_type = compression
                archive.writestr(bad, b"payload")
            with self.subTest(name=name), self.assertRaises(BuildContractError):
                verify_package(output.getvalue())

    def test_cli_pack_verify_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            output_path = Path(tmp) / "package.zip"
            input_path.write_text(json.dumps({
                "package_id": "harbor-demo", "author": "Skeleton original studio",
                "license": "CC0-1.0",
                "files": [{"path": path, "content_base64": base64.b64encode(data).decode()}
                          for path, data in FILES.items()],
            }), encoding="utf-8")
            command = [sys.executable, "-m", "scripts.game.offline_package", "pack",
                       "--input", str(input_path), "--out", str(output_path)]
            packed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            self.assertEqual(json.loads(packed.stdout)["files"], 2)
            verified = subprocess.run([sys.executable, "-m", "scripts.game.offline_package",
                                       "verify", "--archive", str(output_path)],
                                      capture_output=True, text=True, check=False)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["package_digest"],
                             json.loads(packed.stdout)["package_digest"])
            repeated = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(verify_package(output_path.read_bytes())["files"], 2)


if __name__ == "__main__":
    unittest.main()
