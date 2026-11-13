"""Regression contract for immutable offline grid save publication."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session, GameplayContractError
from skeleton.game.gameplay.offline_grid_save import load_slot, save_slot


def campaign():
    return Campaign.load({
        "version": 1, "game_id": "save_demo", "title": "Original Save Demo",
        "license": "CC0-1.0", "author": "Skeleton", "rows": ["#####", "#S.G#", "#####"],
        "objects": [], "quests": [],
        "endings": [{"id": "win", "requires_quests": [], "outcome": "victory"}],
    })


class AtomicGridSaveTests(unittest.TestCase):
    def test_restart_ending_and_no_clobber(self):
        source = campaign()
        session = Session.new(source)
        for index, action in enumerate(("east", "east"), 1):
            session = session.step(Command(str(index), "move", action))
        session = session.step(Command("3", "finish", "win"))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(save_slot(directory, "checkpoint", session), "checkpoint.json")
            restored = load_slot(directory, "checkpoint", source)
            self.assertEqual(restored.ending, "win")
            self.assertEqual(restored.state_digest, session.state_digest)
            with self.assertRaises(FileExistsError):
                save_slot(directory, "checkpoint", Session.new(source))
            self.assertEqual(load_slot(directory, "checkpoint", source).ending, "win")
            self.assertEqual(list(Path(directory).iterdir()), [Path(directory) / "checkpoint.json"])

    def test_corruption_and_foreign_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = campaign()
            save_slot(directory, "one", Session.new(source))
            other = source.spec
            other["game_id"] = "other_game"
            with self.assertRaises(GameplayContractError):
                load_slot(directory, "one", Campaign.load(other))
            (Path(directory) / "one.json").write_text('{"corrupt":', encoding="utf-8")
            with self.assertRaises(GameplayContractError):
                load_slot(directory, "one", source)

    def test_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = campaign()
            for name in ("../outside", "x/y", "", "dot.name"):
                with self.assertRaises(GameplayContractError):
                    save_slot(directory, name, Session.new(source))
            os.symlink("missing", Path(directory) / "alias.json")
            with self.assertRaises(OSError):
                load_slot(directory, "alias", source)
            with self.assertRaises(FileExistsError):
                save_slot(directory, "alias", Session.new(source))

    def test_oversized_and_non_regular(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "huge.json").write_bytes(b"x" * 2_000_001)
            with self.assertRaises(GameplayContractError):
                load_slot(directory, "huge", campaign())
            (Path(directory) / "folder.json").mkdir()
            with self.assertRaises(OSError):
                load_slot(directory, "folder", campaign())


if __name__ == "__main__":
    unittest.main()
