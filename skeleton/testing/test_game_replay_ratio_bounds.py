"""Replay numeric admission must reject adversarial integer sizes without leaking OverflowError."""

import unittest

from skeleton.simulation.game.replay import GameReplayError, _ratio_to_mille


class ReplayRatioBoundsTests(unittest.TestCase):
    def test_valid_ratio_is_deterministic(self):
        self.assertEqual(_ratio_to_mille(0.5), 500)
        self.assertEqual(_ratio_to_mille(2), 2000)

    def test_unbounded_integer_fails_closed(self):
        with self.assertRaises(GameReplayError):
            _ratio_to_mille(10 ** 1000)

    def test_malformed_ratio_fails_closed(self):
        for value in (True, None, -1, float("inf"), float("nan"), "1"):
            with self.subTest(value=repr(value)), self.assertRaises(GameReplayError):
                _ratio_to_mille(value)


if __name__ == "__main__":
    unittest.main()
