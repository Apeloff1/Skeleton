"""Restart, tamper, malformed schema and byte-bound checkpoint regressions."""
import json
import unittest

from skeleton.simulation.fixed_tick import FixedTickReplay, InputEvent, ReplayError
from skeleton.simulation.replay_checkpoint import encode, decode, MAX_CHECKPOINT_BYTES


class CheckpointCodecTests(unittest.TestCase):
    def sample(self):
        replay = FixedTickReplay(seed=71)
        replay.advance((InputEvent(1, "right", True),))
        replay.advance((InputEvent(2, "interact", True),))
        return replay

    def test_restart_replay_identity(self):
        replay = self.sample()
        restored = decode(encode(replay))
        self.assertEqual(restored.digest, replay.digest)
        self.assertEqual(restored.frames, replay.frames)
        self.assertEqual(encode(restored), encode(replay))

    def test_empty_checkpoint(self):
        self.assertEqual(decode(encode(FixedTickReplay())).tick, 0)

    def test_tampered_input_fails_closed(self):
        obj = json.loads(encode(self.sample()))
        obj["frames"][0]["events"][0]["action"] = "left"
        with self.assertRaises(ReplayError):
            decode(json.dumps(obj).encode())

    def test_foreign_seed_fails_closed(self):
        obj = json.loads(encode(self.sample()))
        obj["seed"] = 72
        with self.assertRaises(ReplayError):
            decode(json.dumps(obj).encode())

    def test_missing_or_extra_field_fails_closed(self):
        obj = json.loads(encode(self.sample()))
        del obj["head"]
        with self.assertRaises(ReplayError):
            decode(json.dumps(obj).encode())
        obj["head"] = "0" * 64
        obj["authority_override"] = True
        with self.assertRaises(ReplayError):
            decode(json.dumps(obj).encode())

    def test_boolean_numeric_and_nonboolean_pressed_rejected(self):
        for key in ("hz", "seed"):
            obj = json.loads(encode(self.sample()))
            obj[key] = True
            with self.assertRaises(ReplayError):
                decode(json.dumps(obj).encode())
        obj = json.loads(encode(self.sample()))
        obj["frames"][0]["events"][0]["pressed"] = 1
        with self.assertRaises(ReplayError):
            decode(json.dumps(obj).encode())

    def test_invalid_encoding_and_oversize(self):
        for payload in (b"not json", b"\\xff", b"NaN", b"[]",
                        b"x" * (MAX_CHECKPOINT_BYTES + 1)):
            with self.assertRaises(ReplayError):
                decode(payload)
        with self.assertRaises(ReplayError):
            decode("not bytes")

    def test_input_is_not_mutated(self):
        replay = self.sample()
        original = replay.frames
        decode(encode(replay))
        self.assertEqual(original, replay.frames)


if __name__ == "__main__":
    unittest.main()
