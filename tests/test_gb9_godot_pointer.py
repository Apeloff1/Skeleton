from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.artifact_plane.godot_engine import binary as godot_engine_binary
from skeleton.artifact_plane.godot_locate import GodotLocator


class GB9GodotPointerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "backend").mkdir()
        (self.root / "godot.pointer").write_text(
            "https://github.com/godotengine/godot/releases\n", encoding="utf-8"
        )
        self._write_manifest(b"fixture-godot")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_manifest(self, payload: bytes, *, sha256: str | None = None) -> None:
        digest = hashlib.sha256(payload).hexdigest() if sha256 is None else sha256
        (self.root / "backend" / "godot.artifact.json").write_text(
            json.dumps(
                {
                    "source": "https://github.com/godotengine/godot/releases",
                    "bytes": len(payload),
                    "sha256": digest,
                    "stored_prose": 0,
                }
            ),
            encoding="utf-8",
        )

    def test_missing_binary_is_card(self) -> None:
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["kind"], "godot-binary")
        self.assertEqual(card["found"], 0)
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["law"], "GB-9")
        self.assertEqual(card["stored_prose"], 0)
        self.assertTrue(str(card["hint"]).startswith("pointer:"))

    def test_engine_alias_does_not_raise(self) -> None:
        card = godot_engine_binary.locate(self.root)
        self.assertEqual(card["found"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_matching_local_binary_hits(self) -> None:
        payload = b"fixture-godot"
        path = self.root / "backend" / "godot"
        path.write_bytes(payload)
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 1)
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["sha256"], hashlib.sha256(payload).hexdigest())

    def test_wrong_digest_fails_closed(self) -> None:
        path = self.root / "backend" / "godot"
        path.write_bytes(b"fixture-godot")
        self._write_manifest(b"fixture-godot", sha256="0" * 64)
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 0)
        self.assertEqual(card["hit"], 0)

    def test_null_digest_fails_closed(self) -> None:
        path = self.root / "backend" / "godot"
        path.write_bytes(b"fixture-godot")
        manifest = self.root / "backend" / "godot.artifact.json"
        manifest.write_text(json.dumps({"sha256": None}), encoding="utf-8")
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 0)

    def test_environment_candidate_is_also_verified(self) -> None:
        payload = b"fixture-godot"
        external = self.root / "external-godot"
        external.write_bytes(payload)
        with patch.dict(os.environ, {"SKELETON_GODOT_BIN": str(external)}, clear=False):
            card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 1)
        self.assertEqual(card["hint"], "env:SKELETON_GODOT_BIN")

    def test_environment_candidate_wrong_digest_is_rejected(self) -> None:
        external = self.root / "external-godot"
        external.write_bytes(b"tampered")
        with patch.dict(os.environ, {"SKELETON_GODOT_BIN": str(external)}, clear=False):
            card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 0)

    def test_card_json_roundtrip(self) -> None:
        card = GodotLocator(self.root).locate()
        restored = json.loads(json.dumps(card))
        self.assertEqual(restored["stored_prose"], 0)


if __name__ == "__main__":
    unittest.main()
