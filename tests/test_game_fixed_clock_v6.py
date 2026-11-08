"""Deterministic positive, negative, restart and overload clock fixtures."""
import unittest

from skeleton.simulation.game.fixed_clock import (
    ClockBoundaryError, ClockState, advance_clock,
)


class FixedClockTests(unittest.TestCase):
    def test_partitioned_elapsed_and_restart(self):
        start = ClockState(step_us=10_000)
        a = advance_clock(start, 15_000)
        b = advance_clock(a.after, 15_000)
        restarted = ClockState.from_record(a.after.to_record())
        self.assertEqual(advance_clock(restarted, 15_000).after, b.after)
        self.assertEqual(b.after, advance_clock(start, 30_000).after)
        self.assertEqual(b.ticks, (2, 3))
        self.assertEqual(b.replay_digest, advance_clock(restarted, 15_000).replay_digest)

    def test_overload_drops_work_without_spiral(self):
        result = advance_clock(ClockState(step_us=10_000), 100_000, max_steps=3)
        self.assertEqual(result.ticks, (1, 2, 3))
        self.assertEqual(result.dropped_this_advance_us, 70_000)
        self.assertEqual(result.after.dropped_us, 70_000)
        self.assertEqual(advance_clock(result.after, 0).ticks, ())

    def test_invalid_checkpoints_and_inputs_fail_closed(self):
        for value in (True, 1.0, -1, None, 10_000_001):
            with self.subTest(value=value):
                with self.assertRaises(ClockBoundaryError):
                    advance_clock(ClockState(), value)
        for value in (True, 0, 9):
            with self.assertRaises(ClockBoundaryError):
                advance_clock(ClockState(), 0, max_steps=value)
        with self.assertRaises(ClockBoundaryError):
            ClockState.from_record({"schema": "old"})
        with self.assertRaises(ClockBoundaryError):
            ClockState.from_record({**ClockState().to_record(), "tick": True})
        with self.assertRaises(ClockBoundaryError):
            ClockState(remainder_us=16_667)

    def test_replay_digest_detects_elapsed_divergence(self):
        state = ClockState()
        self.assertNotEqual(
            advance_clock(state, 16_667).replay_digest,
            advance_clock(state, 16_668).replay_digest,
        )
        self.assertEqual(state.digest(), ClockState.from_record(state.to_record()).digest())


if __name__ == "__main__":
    unittest.main()
