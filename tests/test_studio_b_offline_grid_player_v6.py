"""Positive, negative and restart acceptance for offline text-grid player."""
import tempfile
import unittest
from pathlib import Path

from skeleton.game.gameplay.offline_grid_campaign import Campaign, GameplayContractError
from skeleton.game.gameplay.offline_grid_player import interpret, play


def fixture():
    return Campaign.load({
        "version": 1, "game_id": "first_playable", "title": "First_Playable",
        "author": "Skeleton", "license": "CC0-1.0",
        "rows": ["#####", "#S.G#", "#####"],
        "objects": [], "quests": [],
        "endings": [{"id": "victory", "requires_quests": [], "outcome": "victory"}],
    })


class OfflinePlayerTests(unittest.TestCase):
    def test_keyboard_to_real_ending(self):
        commands = iter(["d", "d", "finish victory"])
        lines = []
        with tempfile.TemporaryDirectory() as directory:
            session = play(fixture(), Path(directory), input_fn=lambda _: next(commands),
                           output=lines.append)
        self.assertEqual(session.ending, "victory")
        self.assertEqual(session.tick, 3)
        self.assertTrue(any("ENDING: victory" in line for line in lines))

    def test_save_quit_restart_load_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            first = iter(["d", "save checkpoint", "quit"])
            session = play(fixture(), Path(directory), input_fn=lambda _: next(first),
                           output=lambda _: None)
            self.assertEqual(session.tick, 1)
            second = iter(["load checkpoint", "d", "finish victory"])
            restored = play(fixture(), Path(directory), input_fn=lambda _: next(second),
                            output=lambda _: None)
            self.assertEqual(restored.ending, "victory")
            self.assertEqual(restored.tick, 3)

    def test_reject_collision_and_invalid_action_without_state_mutation(self):
        commands = iter(["a", "finish victory", "d", "d", "finish victory"])
        messages = []
        with tempfile.TemporaryDirectory() as directory:
            session = play(fixture(), Path(directory), input_fn=lambda _: next(commands),
                           output=messages.append)
        self.assertEqual(session.tick, 3)
        self.assertEqual(sum(line.startswith("Rejected:") for line in messages), 2)

    def test_reject_bad_commands(self):
        for value in ("", "finish", "d extra", "move north", "x" * 129):
            with self.subTest(value=value):
                with self.assertRaises(GameplayContractError):
                    interpret(value, "1")

    def test_reject_corrupt_checkpoint_and_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "bad.json").write_text("{broken", encoding="utf-8")
            commands = iter(["load bad", "d", "d", "finish victory"])
            messages = []
            session = play(fixture(), Path(directory), input_fn=lambda _: next(commands),
                           output=messages.append)
            self.assertEqual(session.ending, "victory")
            self.assertTrue(any("Rejected:" in line for line in messages))


if __name__ == "__main__":
    unittest.main()
