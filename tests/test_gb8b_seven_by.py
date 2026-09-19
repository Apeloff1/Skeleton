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

    def test_composite_plane_fails_closed_when_seven_by_fails(self) -> None:
        plane = ArtifactPlane.__new__(ArtifactPlane)
        plane.track_e = Mock(audit=Mock(return_value={"hit": 1}))
        plane.seven_by = Mock(audit=Mock(return_value={"hit": 0}))
        plane.godot = Mock(locate=Mock(return_value={"hit": 1}))

        card = plane.snapshot()

        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["law"], "GB-8/GB-8b")
        self.assertEqual(card["seven_by"]["hit"], 0)


if __name__ == "__main__":
    unittest.main()
