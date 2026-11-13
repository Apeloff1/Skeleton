"""Positive, negative and replay fixtures for bounded simulation input."""
import unittest

from skeleton.game.simulation.flgb_simulation_runtime import (
    AABB, CharacterController, SimulationContractError,
)
from skeleton.game.simulation.input_collision import MovementInput, step_character


class MovementCollisionTests(unittest.TestCase):
    def setUp(self):
        self.player = CharacterController("hero", (0, 0, 0), 100, True)

    def test_deterministic_movement_and_replay(self):
        actions = [MovementInput(1000, 0), MovementInput(0, 1000)]
        def run():
            player = self.player
            trace = []
            for action in actions:
                result = step_character(player, action, 100_000_000, ())
                player = result.controller
                trace.append(player.position)
            return trace
        self.assertEqual(run(), run())
        self.assertEqual(run(), [(10, 0, 0), (10, 10, 0)])

    def test_wall_blocks_swept_movement(self):
        wall = AABB("wall", (5, -5, -5), (6, 5, 5))
        result = step_character(self.player, MovementInput(1000, 0), 100_000_000, (wall,))
        self.assertEqual(result.controller.position, (0, 0, 0))
        self.assertTrue(result.blocked_x)

    def test_collision_slides_on_free_axis(self):
        wall = AABB("wall", (5, -5, -5), (6, 5, 5))
        result = step_character(self.player, MovementInput(1000, 1000), 100_000_000, (wall,))
        self.assertTrue(result.blocked_x)
        self.assertGreater(result.controller.position[1], 0)

    def test_reject_invalid_axes_and_steps(self):
        for axis in (True, 1001, 0.5, None):
            with self.assertRaises(SimulationContractError):
                MovementInput(axis, 0)
        for step in (True, 0, -1, 100_000_001):
            with self.assertRaises(SimulationContractError):
                step_character(self.player, MovementInput(1000, 0), step, ())

    def test_reject_duplicate_or_self_colliders(self):
        box = AABB("wall", (3, 0, 0), (4, 2, 2))
        with self.assertRaises(SimulationContractError):
            step_character(self.player, MovementInput(0, 0), 1, (box, box))
        self_box = AABB("hero", (3, 0, 0), (4, 2, 2))
        with self.assertRaises(SimulationContractError):
            step_character(self.player, MovementInput(0, 0), 1, (self_box,))

    def test_restart_from_immutable_position(self):
        first = step_character(self.player, MovementInput(1000, 0), 100_000_000, ())
        restored = CharacterController("hero", first.controller.position, 100, True)
        second = step_character(restored, MovementInput(1000, 0), 100_000_000, ())
        self.assertEqual(second.controller.position, (20, 0, 0))
        self.assertEqual(self.player.position, (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
