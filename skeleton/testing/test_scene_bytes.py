"""Offline scene byte boundary: real canonical replay, no mocked verifier."""
import json
import unittest

from skeleton.game.gameplay.scene_travel import (
    new_session, original_demo, resume_session, verify_session,
)
from skeleton.game.gameplay.offline_portable import PortableGameError, MAX_PORTABLE_BYTES
from skeleton.game.gameplay.scene_bytes import encode_scene_bytes, decode_scene_bytes


class SceneByteTransportTests(unittest.TestCase):
    def setUp(self):
        world, actions = original_demo()
        self.world = world
        self.actions = actions

    def test_cold_resume_to_legitimate_ending(self):
        initial = new_session(self.world)
        mid = resume_session(initial, self.actions[:1])
        loaded = decode_scene_bytes(encode_scene_bytes(mid))
        finished = resume_session(loaded, self.actions[1:])
        self.assertEqual(finished["state"]["phase"], "won")
        self.assertEqual(verify_session(finished), finished)

    def test_stable_round_trip(self):
        session = resume_session(new_session(self.world), self.actions)
        payload = encode_scene_bytes(session)
        self.assertEqual(encode_scene_bytes(decode_scene_bytes(payload)), payload)

    def test_reject_duplicate_keys_even_with_valid_last_value(self):
        payload = encode_scene_bytes(new_session(self.world))
        duplicate = payload[:-1] + b',"kind":"skeleton.scene_travel.v1"}'
        with self.assertRaises(PortableGameError):
            decode_scene_bytes(duplicate)

    def test_reject_invalid_utf8(self):
        with self.assertRaises(PortableGameError):
            decode_scene_bytes(b"\xff")

    def test_reject_nonfinite_json(self):
        with self.assertRaises(PortableGameError):
            decode_scene_bytes(b'{"value":NaN}')

    def test_reject_exponent_overflow_before_scene_replay(self):
        # JSON permits exponent syntax; Python may decode it to infinite float.
        with self.assertRaisesRegex(PortableGameError, "nonfinite portable gameplay number"):
            decode_scene_bytes(b'{"value":1e1000000}')

    def test_reject_over_budget_before_parse(self):
        with self.assertRaises(PortableGameError):
            decode_scene_bytes(b" " * (MAX_PORTABLE_BYTES + 1))

    def test_reject_tampered_checkpoint(self):
        payload = json.loads(encode_scene_bytes(new_session(self.world)))
        payload["state_digest"] = "0" * 64
        with self.assertRaises(PortableGameError):
            decode_scene_bytes(json.dumps(payload).encode())

    def test_reject_non_bytes(self):
        for value in (None, "", bytearray(b"{}"), memoryview(b"{}")):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(PortableGameError):
                    decode_scene_bytes(value)


if __name__ == "__main__":
    unittest.main()
