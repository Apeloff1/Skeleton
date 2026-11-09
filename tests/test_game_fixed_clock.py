"""Deterministic clock restart and rejection tests."""
import unittest

from skeleton.simulation.game.fixed_clock import FixedClock, FixedClockError


class FixedClockTests(unittest.TestCase):
    def test_step_and_restart_equivalence(self):
        clock = FixedClock(tick_us=10_000)
        first, steps = clock.advance(25_000)
        self.assertEqual((steps, first.tick, first.remainder_us), (2, 2, 5_000))
        restored = FixedClock.restore(first.snapshot())
        self.assertEqual(restored.advance(15_000), first.advance(15_000))

    def test_partition_invariance(self):
        original = FixedClock(tick_us=10_000)
        a, _ = original.advance(50_000)
        b, _ = original.advance(20_000)
        b, _ = b.advance(30_000)
        self.assertEqual(a, b)

    def test_invalid_numeric_inputs(self):
        for value in (True, None, -1, 1.5, 1_000_001):
            with self.subTest(value=value), self.assertRaises(FixedClockError):
                FixedClock().advance(value)

    def test_bounded_catchup(self):
        with self.assertRaises(FixedClockError):
            FixedClock(tick_us=1_000).advance(9_000)

    def test_corrupt_and_foreign_snapshots(self):
        saved = FixedClock().snapshot()
        for mutation in ({"tick": 4}, {"schema": "foreign"}, {"sha256": "0" * 64}, {"extra": 1}):
            with self.subTest(mutation=mutation), self.assertRaises(FixedClockError):
                FixedClock.restore({**saved, **mutation})

    def test_tick_overflow(self):
        with self.assertRaises(FixedClockError):
            FixedClock(tick=1_000_000_000).advance(16_667)


if __name__ == "__main__":
    unittest.main()
