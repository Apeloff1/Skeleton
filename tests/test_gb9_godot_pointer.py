from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
        (self.root / "backend" / "godot.artifact.json").write_text(
            json.dumps({"source": "https://github.com/godotengine/godot/releases", "stored_prose": 0}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

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

    def test_local_gitignored_binary_hits(self) -> None:
        path = self.root / "backend" / "godot"
        path.write_bytes(b"not-really-godot")
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 1)
        self.assertEqual(card["hit"], 1)

    def test_card_json_roundtrip(self) -> None:
        card = GodotLocator(self.root).locate()
        restored = json.loads(json.dumps(card))
        self.assertEqual(restored["stored_prose"], 0)


if __name__ == "__main__":
    unittest.main()
