"""Source-only regression tests for immutable grid campaign save custody."""
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.game.gameplay.grid_save_custody import publish_save, read_save, SaveCustodyError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session

SOURCE = Path(__file__).resolve().parents[2] / "skeleton/game/gameplay/content/lantern_harbor.json"


class GridSaveCustodyTests(unittest.TestCase):
    def setUp(self):
        self.campaign = Campaign.load(json.loads(SOURCE.read_text(encoding="utf-8")))
        self.session = Session.new(self.campaign)

    def test_publish_restore_restart_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "save.json"
            publish_save(target, self.session)
            self.assertEqual(read_save(target, self.campaign).snapshot(), self.session.snapshot())
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                publish_save(target, self.session)
            self.assertEqual(target.read_bytes(), original)

    def test_duplicate_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "save.json"
            target.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(SaveCustodyError):
                read_save(target, self.campaign)

    def test_truncated_save_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "save.json"
            target.write_bytes(b'{"events":')
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                read_save(target, self.campaign)

    def test_foreign_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "save.json"
            publish_save(target, self.session)
            changed = self.campaign.spec
            changed["title"] = "Different Original"
            foreign = Campaign.load(changed)
            with self.assertRaises(ValueError):
                read_save(target, foreign)


if __name__ == "__main__":
    unittest.main()
