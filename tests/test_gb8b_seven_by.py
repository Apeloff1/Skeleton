from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from skeleton.artifact_plane.plane import ArtifactPlane
from skeleton.artifact_plane.seven_by import SevenByAuditor


class GB8bSevenByTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        lane = self.root / "docs" / "archive" / "seven_by"
        lane.mkdir(parents=True)
        (lane / "SEVEN_BY_INDEX.md").write_text("# SEVEN_BY series — archived\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_clean_archive_hits(self) -> None:
        card = SevenByAuditor(self.root).audit()
        self.assertEqual(card["kind"], "seven-by-archive")
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["law"], "GB-8b")
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["stray_root"], [])

    def test_root_volume_fails_closed(self) -> None:
        (self.root / "SEVEN_BY_42.md").write_text("# frozen\n", encoding="utf-8")
        auditor = SevenByAuditor(self.root)
        card = auditor.audit()
        self.assertEqual(card["hit"], 0)
        self.assertIn("SEVEN_BY_42.md", card["stray_root"])
        self.assertEqual(auditor.fail_closed(), 2)

    def test_missing_lane_fails_closed(self) -> None:
        bare = Path(tempfile.mkdtemp())
        try:
            card = SevenByAuditor(bare).audit()
            self.assertEqual(card["hit"], 0)
            self.assertFalse(card["lane_present"])
        finally:
            import shutil
            shutil.rmtree(bare)

    def test_card_json_roundtrip(self) -> None:
        card = SevenByAuditor(self.root).audit()
        restored = json.loads(json.dumps(card))
        self.assertEqual(restored["stored_prose"], 0)

    def _composite_card(self, *, track_hit: int, seven_hit: int) -> dict[str, object]:
        plane = ArtifactPlane.__new__(ArtifactPlane)
        plane.track_e = Mock(audit=Mock(return_value={"hit": track_hit}))
        plane.seven_by = Mock(audit=Mock(return_value={"hit": seven_hit}))
        # Godot is discovery metadata today, not an accepted archive-policy gate.
        plane.godot = Mock(locate=Mock(return_value={"hit": 0}))
        return plane.snapshot()

    def test_composite_plane_accepts_only_when_archive_policies_accept(self) -> None:
        card = self._composite_card(track_hit=1, seven_hit=1)
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["law"], "GB-8/GB-8b")

    def test_composite_plane_fails_closed_when_seven_by_fails(self) -> None:
        card = self._composite_card(track_hit=1, seven_hit=0)
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["seven_by"]["hit"], 0)

    def test_composite_plane_fails_closed_when_track_e_fails(self) -> None:
        card = self._composite_card(track_hit=0, seven_hit=1)
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["track_e"]["hit"], 0)

    def test_composite_plane_fails_closed_when_both_archive_policies_fail(self) -> None:
        card = self._composite_card(track_hit=0, seven_hit=0)
        self.assertEqual(card["hit"], 0)


if __name__ == "__main__":
    unittest.main()
