"""Positive, negative and restart regression for deterministic input replay."""
import unittest

from skeleton.simulation.fixed_tick import FixedTickReplay, InputEvent, ReplayError, ReplayFrame


class FixedTickTests(unittest.TestCase):
    def test_replay_survives_restart(self):
        original = FixedTickReplay(seed=42)
        original.advance((InputEvent(1, "right", True),))
        original.advance((InputEvent(2, "interact", True),))
        recovered = FixedTickReplay.verify(hz=60, seed=42, frames=original.frames)
        self.assertEqual(original.digest, recovered.digest)
        self.assertEqual(original.tick, recovered.tick)

    def test_rejects_tampering_and_foreign_seed(self):
        original = FixedTickReplay(seed=42)
        frame = original.advance((InputEvent(1, "right", True),))
        with self.assertRaises(ReplayError):
            FixedTickReplay.verify(hz=60, seed=43, frames=(frame,))
        tampered = ReplayFrame(frame.tick, (), frame.prior_digest, frame.digest)
        with self.assertRaises(ReplayError):
            FixedTickReplay.verify(hz=60, seed=42, frames=(tampered,))

    def test_rejects_invalid_tick_and_payload(self):
        with self.assertRaises(ReplayError):
            InputEvent(True, "right", True)
        with self.assertRaises(ReplayError):
            InputEvent(1, "execute", True)
        with self.assertRaises(ReplayError):
            InputEvent(1, "right", 1)
        replay = FixedTickReplay()
        with self.assertRaises(ReplayError):
            replay.advance((InputEvent(2, "right", True),))
        self.assertEqual(replay.tick, 0)
        self.assertEqual(len(replay.frames), 0)

    def test_deterministic_independent_runs(self):
        a, b = FixedTickReplay(seed=7), FixedTickReplay(seed=7)
        for tick in range(1, 10):
            events = (InputEvent(tick, "up", tick % 2 == 0),)
            self.assertEqual(a.advance(events), b.advance(events))


if __name__ == "__main__":
    unittest.main()
