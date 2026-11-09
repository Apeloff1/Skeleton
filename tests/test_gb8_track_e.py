from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

from skeleton.artifact_plane import ArtifactPlane, TrackEAuditor, godot_locate
from skeleton.artifact_plane.godot_locate import GodotLocator
from skeleton.artifact_plane.sprawl import RootSprawlIndex


class GB8TrackETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "tests" / "legacy_root").mkdir(parents=True)
        (self.root / "scripts" / "archive_root_tests").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_clean_root_hits(self) -> None:
        card = TrackEAuditor(self.root).audit()
        self.assertEqual(card["kind"], "track-e")
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["law"], "GB-8")
        self.assertEqual(card["stray_root_tests"], [])

    def test_stray_root_test_fails_closed(self) -> None:
        (self.root / "backend_test.py").write_text("assert False\n", encoding="utf-8")
        auditor = TrackEAuditor(self.root)
        card = auditor.audit()
        self.assertEqual(card["hit"], 0)
        self.assertIn("backend_test.py", card["stray_root_tests"])
        self.assertEqual(auditor.fail_closed(), 2)

    def test_test_prefix_at_root_is_sprawl(self) -> None:
        (self.root / "test_accidentally_root.py").write_text("x=1\n", encoding="utf-8")
        card = TrackEAuditor(self.root).audit()
        self.assertIn("test_accidentally_root.py", list(card["stray_root_tests"]))

    def test_bak_at_root_is_sprawl(self) -> None:
        (self.root / "backend_test.py.bak_1").write_text("old\n", encoding="utf-8")
        card = TrackEAuditor(self.root).audit()
        self.assertEqual(card["hit"], 0)
        self.assertIn("backend_test.py.bak_1", card["stray_bak"])

    def test_seven_by_deferred_not_fail_closed(self) -> None:
        (self.root / "SEVEN_BY_NOTE.md").write_text("# hold\n", encoding="utf-8")
        card = TrackEAuditor(self.root).audit()
        self.assertEqual(card["hit"], 1)
        self.assertIn("SEVEN_BY_NOTE.md", card["seven_by_deferred"])

    def test_godot_missing_does_not_raise(self) -> None:
        card = godot_locate(self.root)
        self.assertEqual(card["kind"], "godot-binary")
        self.assertEqual(card["found"], 0)
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_godot_pointer_hint(self) -> None:
        (self.root / "godot.pointer").write_text("lfs://godot-engine\n", encoding="utf-8")
        card = GodotLocator(self.root).locate()
        self.assertEqual(card["found"], 0)
        self.assertTrue(str(card["hint"]).startswith("pointer:"))

    def test_godot_env_file(self) -> None:
        binary = self.root / "godot.bin"
        binary.write_bytes(b"not-really-godot")
        import os

        previous = os.environ.get("SKELETON_GODOT_BIN")
        os.environ["SKELETON_GODOT_BIN"] = str(binary)
        try:
            card = GodotLocator(self.root).locate()
        finally:
            if previous is None:
                os.environ.pop("SKELETON_GODOT_BIN", None)
            else:
                os.environ["SKELETON_GODOT_BIN"] = previous
        self.assertEqual(card["found"], 1)
        self.assertEqual(card["hit"], 1)

    def test_plane_snapshot_composes(self) -> None:
        snap = ArtifactPlane(self.root).snapshot()
        self.assertEqual(snap["kind"], "artifact-plane")
        self.assertEqual(snap["stored_prose"], 0)
        self.assertEqual(snap["track_e"]["law"], "GB-8")
        self.assertEqual(snap["godot"]["kind"], "godot-binary")

    def test_package_import_does_not_require_godot(self) -> None:
        module = importlib.import_module("skeleton.artifact_plane")
        self.assertTrue(hasattr(module, "godot_locate"))
        self.assertTrue(hasattr(module, "TrackEAuditor"))

    def test_card_json_roundtrip(self) -> None:
        card = TrackEAuditor(self.root).audit()
        blob = json.dumps(card)
        restored = json.loads(blob)
        self.assertEqual(restored["stored_prose"], 0)


if __name__ == "__main__":
    unittest.main()
