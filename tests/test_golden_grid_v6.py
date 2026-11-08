"""Deterministic positive, adversarial and cold-restore grid gameplay tests."""
import json
import unittest

from skeleton.simulation.game.golden_grid import (
    GridState, GameplayError, checkpoint, play, restore, step,
)

PROJECT = "a" * 64


class GoldenGridTests(unittest.TestCase):
    def test_quest_ending_and_restart(self):
        # Reach the NPC from the top, start quest, fetch key via lower corridor,
        # return to NPC, then travel around the right edge to the exit.
        to_npc = ["right"] * 4 + ["down", "interact"]
        # The central wall blocks (2, 1..3). Traverse the upper corridor.
        to_key = ["up"] + ["left"] * 3 + ["down"] * 3
        back_to_npc = ["up"] * 3 + ["right"] * 3 + ["down", "interact"]
        to_exit = ["right"] + ["down"] * 3 + ["interact"]
        actions = to_npc + to_key + back_to_npc + to_exit
        final = play(actions)
        self.assertTrue(final.ending)
        halfway = play(to_npc + to_key)
        restored = restore(checkpoint(halfway, project_sha256=PROJECT), project_sha256=PROJECT)
        self.assertEqual(play(back_to_npc + to_exit, restored), final)
        self.assertEqual(play(actions), final)

    def test_wall_and_boundary(self):
        state = play(["right", "right", "down"])
        self.assertEqual((state.x, state.y), (2, 0))
        self.assertEqual((step(state, "down").x, step(state, "down").y), (2, 0))
        self.assertEqual((step(GridState(), "left").x, step(GridState(), "left").y), (0, 0))

    def test_corrupt_foreign_and_duplicate_checkpoint(self):
        raw = checkpoint(GridState(), project_sha256=PROJECT)
        with self.assertRaises(GameplayError):
            restore(raw, project_sha256="b" * 64)
        with self.assertRaises(GameplayError):
            restore(raw.replace('"tick":0', '"tick":1'), project_sha256=PROJECT)
        with self.assertRaises(GameplayError):
            restore(raw.replace('"schema":', '"schema":"extra","schema":'), project_sha256=PROJECT)

    def test_invalid_actions_and_impossible_state(self):
        for bad in (None, True, 1, "", "teleport"):
            with self.subTest(bad=bad), self.assertRaises(GameplayError):
                step(GridState(), bad)
        with self.assertRaises(GameplayError):
            GridState(tick=True)
        with self.assertRaises(GameplayError):
            GridState(quest_completed=True)
        with self.assertRaises(GameplayError):
            GridState(x=2, y=2)
        with self.assertRaises(GameplayError):
            play(["wait"] * 4097)


if __name__ == "__main__":
    unittest.main()
