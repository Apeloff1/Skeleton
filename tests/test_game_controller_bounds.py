"""Regression for bounded deterministic character movement."""
import unittest

from skeleton.game.simulation.character_controller import CharacterController, SimulationContractError


class ControllerBoundsTest(unittest.TestCase):
    def setUp(self):
        self.player = CharacterController("player", (0, 0, 0), 120, True)

    def test_valid_fixed_step_and_reconstruction(self):
        next_player = self.player.move((2, -2, 0), 20_000_000)
        self.assertEqual(next_player.position, (2, -2, 0))
        self.assertEqual(next_player.move((-2, 2, 0), 20_000_000), self.player)
        self.assertEqual(self.player.position, (0, 0, 0))

    def test_reject_invalid_clock_inputs(self):
        for step in (False, True, 0, -1, 1.0, None, "20", 1_000_000_001):
            with self.subTest(step=step), self.assertRaises(SimulationContractError):
                self.player.move((0, 0, 0), step)

    def test_reject_overspeed_and_malformed_delta(self):
        for delta in ((3, 0, 0), (True, 0, 0), (0, 0), [0, 0, 0], (10**16, 0, 0)):
            with self.subTest(delta=delta), self.assertRaises(SimulationContractError):
                self.player.move(delta, 20_000_000)

    def test_reject_world_overflow_and_preserve_original(self):
        edge = CharacterController("player", (10**15, 0, 0), 120, True)
        with self.assertRaises(SimulationContractError):
            edge.move((1, 0, 0), 20_000_000)
        self.assertEqual(edge.position, (10**15, 0, 0))


if __name__ == "__main__":
    unittest.main()
