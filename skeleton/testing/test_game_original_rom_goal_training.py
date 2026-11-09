"""Source-executed original Game Boy objective training, no commercial ROMs.

Positive test runs original CPU ROM instructions and stores replay-verified
mission progress in Q values; it does NOT prove third-party emulator hardware
accuracy or change production transformer weights. No tests executed here.
"""

from __future__ import annotations

import unittest

from skeleton.jeeves.game_original_rom_goal_training import (
    HEIGHT,
    WIDTH,
    OriginalGameGoalError,
    _generated,
    _route,
    train_original_rom_goal_policy,
)


class GeneratedOriginalGoalSourceTests(unittest.TestCase):
    def test_mission_route_is_drawn_from_the_actual_generated_source(self):
        rom, manifest = _generated(42)
        self.assertEqual(len(rom), 32768)
        self.assertEqual(manifest["mapper"], "rom_only")
        self.assertEqual(manifest["memory_observations"]["completed"], 0xC004)

    def test_maze_route_from_source_tilemap_has_no_wall_crossings(self):
        grid = [[2] * WIDTH for _ in range(HEIGHT)]
        for x in range(1, 18):
            grid[1][x] = 0
        for y in range(1, 16):
            grid[y][17] = 0
        grid[15][17] = 3
        path = _route(grid, (1, 1))
        self.assertEqual(len(path), 30)
        self.assertEqual(path[0], ("right", (2, 1)))
        self.assertEqual(path[-1], ("down", (17, 15)))
        for action, (x, y) in path:
            self.assertIn(action, ("left", "right", "up", "down"))
            self.assertNotEqual(grid[y][x], 2)

    def test_unreachable_original_objective_is_rejected(self):
        grid = [[2] * WIDTH for _ in range(HEIGHT)]
        grid[1][1] = 0
        grid[15][17] = 3
        with self.assertRaises(OriginalGameGoalError):
            _route(grid, (1, 1))

    def test_source_executed_original_rom_completes_and_trains_q(self):
        evidence = train_original_rom_goal_policy(
            seed=42, max_steps=2048, max_frames_per_tile=16,
        )
        self.assertTrue(evidence["source_actual_goal_completion"])
        self.assertEqual(evidence["observed_start"]["score"], 0)
        self.assertEqual(evidence["observed_active_end"]["completed"], 1)
        self.assertGreaterEqual(evidence["observed_active_end"]["score"], 1)
        self.assertEqual(evidence["observed_neutral_end"]["completed"], 0)
        self.assertEqual(
            evidence["independently_replayed_source_frames"],
            evidence["executed_input_frames"],
        )
        self.assertEqual(
            evidence["real_goal_conditioned_q_updates"],
            evidence["executed_input_frames"],
        )
        self.assertEqual(
            evidence["q_policy_snapshot"]["committed_updates"],
            evidence["real_goal_conditioned_q_updates"],
        )
        self.assertFalse(evidence["hardware_accuracy_certified"])
        self.assertFalse(evidence["production_policy_promotion"])
        self.assertEqual(evidence["neural_weights_updated"], 0)

    def test_source_simulation_work_is_strictly_bounded(self):
        for options in (
            {"seed": -1},
            {"max_steps": 10},
            {"max_steps": 1000000},
            {"max_frames_per_tile": 0},
            {"max_frames_per_tile": 1000},
        ):
            with self.subTest(options=options):
                with self.assertRaises(OriginalGameGoalError):
                    train_original_rom_goal_policy(**options)


if __name__ == "__main__":
    unittest.main()
