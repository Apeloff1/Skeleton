"""Fail-closed checkpoint codec tests for exact deterministic restart custody."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from skeleton.simulation.fixed_tick import (
    FixedTickReplay, InputEvent, ReplayError,
)
from skeleton.simulation import replay_checkpoint as codec


def sample() -> FixedTickReplay:
    replay = FixedTickReplay(seed=91)
    replay.advance((InputEvent(1, "right", True),))
    replay.advance((InputEvent(2, "attack", True),))
    replay.advance((InputEvent(3, "attack", False), InputEvent(3, "pause", True)))
    return replay


class StreamingCheckpointTests(unittest.TestCase):
    def test_streaming_encoder_matches_canonical_sorted_json(self) -> None:
        replay = sample()
        parsed = json.loads(codec.encode(replay))
        canonical = json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        self.assertEqual(codec.encode(replay), canonical)
        self.assertEqual(codec.decode(canonical).digest, replay.digest)

    def test_source_is_not_mutated_by_round_trip(self) -> None:
        replay = sample()
        frames_before = replay.frames
        digest_before = replay.digest
        restored = codec.decode(codec.encode(replay))
        self.assertEqual(restored.frames, frames_before)
        self.assertEqual(restored.digest, digest_before)
        self.assertEqual(replay.frames, frames_before)

    def test_encoder_fails_when_byte_budget_is_exceeded_early(self) -> None:
        replay = sample()
        with patch.object(codec, "MAX_CHECKPOINT_BYTES", 80):
            with self.assertRaisesRegex(ReplayError, "byte budget"):
                codec.encode(replay)

    def test_decoder_rejects_duplicate_top_level_keys(self) -> None:
        data = codec.encode(sample())
        malformed = data[:-1] + b',"head":"' + b"0" * 64 + b'"}'
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            codec.decode(malformed)

    def test_decoder_rejects_duplicate_frame_keys(self) -> None:
        obj = json.loads(codec.encode(sample()))
        data = json.dumps(obj, separators=(",", ":")).encode()
        data = data.replace(b'"prior":', b'"prior":"tampered","prior":', 1)
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            codec.decode(data)

    def test_decoder_rejects_duplicate_event_keys(self) -> None:
        obj = json.loads(codec.encode(sample()))
        data = json.dumps(obj, separators=(",", ":")).encode()
        data = data.replace(b'"action":', b'"action":"unknown","action":', 1)
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            codec.decode(data)

    def test_float_exponents_and_nonfinite_tokens_are_rejected(self) -> None:
        canonical = codec.encode(sample())
        for payload in (
            canonical.replace(b'"hz":60', b'"hz":6e1', 1),
            canonical.replace(b'"seed":91', b'"seed":9.1e1', 1),
            canonical.replace(b'"hz":60', b'"hz":NaN', 1),
            canonical.replace(b'"hz":60', b'"hz":Infinity', 1),
        ):
            with self.subTest(payload=payload[-120:]):
                with self.assertRaises(ReplayError):
                    codec.decode(payload)

    def test_boolean_and_out_of_range_controls_do_not_coerce(self) -> None:
        for key, value in (
            ("hz", True), ("hz", 0), ("hz", 241),
            ("seed", True), ("seed", -1), ("seed", 2**63),
        ):
            with self.subTest(field=key, value=value):
                obj = json.loads(codec.encode(sample()))
                obj[key] = value
                with self.assertRaises(ReplayError):
                    codec.decode(json.dumps(obj).encode())

    def test_invalid_bytes_and_oversize_are_denied_before_parsing(self) -> None:
        for value in (None, "text", bytearray(b"{}"), b"\xff", b"x" * 64):
            with self.subTest(value=type(value).__name__):
                with patch.object(codec, "MAX_CHECKPOINT_BYTES", 32):
                    with self.assertRaises(ReplayError):
                        codec.decode(value)

    def test_tampered_frame_or_event_does_not_pass_hash_chain(self) -> None:
        base = json.loads(codec.encode(sample()))
        for change in ("action", "frame-digest", "prior", "pressed"):
            obj = json.loads(json.dumps(base))
            if change == "action":
                obj["frames"][0]["events"][0]["action"] = "left"
            elif change == "frame-digest":
                obj["frames"][0]["digest"] = "0" * 64
            elif change == "prior":
                obj["frames"][1]["prior"] = "f" * 64
            else:
                obj["frames"][0]["events"][0]["pressed"] = False
            with self.subTest(change=change), self.assertRaises(ReplayError):
                codec.decode(json.dumps(obj).encode())

    def test_checkpoint_head_matches_actual_last_frame(self) -> None:
        encoded = codec.encode(sample())
        obj = json.loads(encoded)
        self.assertEqual(obj["head"], obj["frames"][-1]["digest"])
        self.assertEqual(codec.decode(encoded).digest, obj["head"])

    def test_source_corruption_cannot_be_certified_by_encoder(self) -> None:
        replay = sample()
        replay._frames[-1] = type(replay.frames[-1])(
            replay.frames[-1].tick,
            replay.frames[-1].events,
            replay.frames[-1].prior_digest,
            "0" * 64,
        )
        with self.assertRaises(ReplayError):
            codec.encode(replay)


if __name__ == "__main__":
    unittest.main()
