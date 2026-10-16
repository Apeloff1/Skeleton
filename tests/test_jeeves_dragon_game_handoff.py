"""Focused Dragon -> Jeeves local game handoff regression tests.

Run explicitly with python -m unittest tests.test_jeeves_dragon_game_handoff.
Not part of the fast merge gates.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skeleton.developer.game_cli import SCHEMA as GAME_SCHEMA
from skeleton.developer.jeeves_game_dragon import (
    adopt, ingest, load_handoff, plan, review,
)


class DragonJeevesGameHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name) / "dragon-studio"
        self.root.mkdir()
        (self.root / "design").mkdir()
        self.config = {
            "schema": GAME_SCHEMA, "name": "dragon-studio",
            "vision": "An original exploration game", "era": "extraction_now",
            "archetype": "auto",
        }
        (self.root / "skeleton.game.json").write_text(json.dumps(self.config))
        self.source = "design/dragon_study.json"
        self.packet = {
            "schema": "skeleton.dragon.jeeves_study.v1",
            "project": "dragon-studio", "owner": "local-reviewer",
            "game_label": "Operator-owned reference session",
            "duration_ms": 8000, "capture_consent": True,
            "analysis_consent": True, "rights_attested": True,
            "observations": [{
                "timestamp_ms": 1000, "source_frame_ms": 1000,
                "label": "player movement", "confidence": 0.98,
                "description": "Smooth acceleration and readable stopping",
                "mechanic": "movement", "preference": "enjoyed",
                "user_confirmed": True, "reviewer_note": "Confirmed in review",
            }],
        }
        self._write_packet()

    def _write_packet(self) -> None:
        (self.root / self.source).write_text(json.dumps(self.packet))

    def _ingest(self) -> dict:
        inspection = review(self.root, source=self.source)
        return ingest(self.root, source=self.source,
                      approved_sha256=inspection["source_sha256"])

    def test_read_only_review_and_exact_ingest_approval(self) -> None:
        inspection = review(self.root, source=self.source)
        self.assertTrue(inspection["ok"])
        self.assertFalse((self.root / ".jeeves").exists())
        with self.assertRaises(PermissionError):
            ingest(self.root, source=self.source, approved_sha256="0" * 64)
        saved = self._ingest()
        self.assertEqual(saved["reviewed_events"], 1)
        self.assertFalse(saved["raw_video_retained"])
        self.assertEqual(self._ingest()["session_sha256"], saved["session_sha256"])

    def test_original_forge_requires_handoff_approval(self) -> None:
        self._ingest()
        preview = plan(self.root, source=self.source,
                       genre="platformer", target="gameboy")
        self.assertTrue(preview["handoff"]["original_assets_required"])
        self.assertFalse(preview["handoff"]["game_implementation_verified"])
        self.assertFalse(preview["approved_for_model_context"])
        self.assertEqual(preview["handoff"]["prototype"]["mechanics"][0]["mechanic"],
                         "movement")
        with self.assertRaises(PermissionError):
            adopt(self.root, source=self.source, genre="platformer",
                  target="gameboy", approved_sha256="0" * 64)
        published = adopt(self.root, source=self.source, genre="platformer",
                          target="gameboy", approved_sha256=preview["handoff_sha256"])
        self.assertEqual(published["handoff_sha256"], preview["handoff_sha256"])
        checked = load_handoff(self.root, published["handoff_sha256"])
        self.assertEqual(checked["source_sha256"], preview["handoff"]["source_sha256"])
        with self.assertRaises(ValueError):
            adopt(self.root, source=self.source, genre="platformer",
                  target="gameboy", approved_sha256=preview["handoff_sha256"])

    def test_source_change_and_tamper_fail_closed(self) -> None:
        self._ingest()
        preview = plan(self.root, source=self.source,
                       genre="platformer", target="gameboy")
        saved = adopt(self.root, source=self.source, genre="platformer",
                      target="gameboy", approved_sha256=preview["handoff_sha256"])
        handoff_path = Path(saved["path"])
        handoff_path.write_text(handoff_path.read_text().replace("platformer", "rpg"))
        with self.assertRaises(ValueError):
            load_handoff(self.root, saved["handoff_sha256"])

    def test_reject_unconfirmed_preference_and_rights(self) -> None:
        self.packet["observations"][0]["user_confirmed"] = False
        self._write_packet()
        with self.assertRaises(PermissionError):
            review(self.root, source=self.source)
        self.packet["observations"][0]["user_confirmed"] = True
        self.packet["rights_attested"] = False
        self._write_packet()
        with self.assertRaises(PermissionError):
            review(self.root, source=self.source)


if __name__ == "__main__":
    unittest.main()
