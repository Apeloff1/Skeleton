"""Source-bound and adversarial custody regressions for environment + replay codecs.

Tests run offline without network, Godot, native hardware or provider services.
A green source suite is not device, Docker or release certification.
"""
from __future__ import annotations

from dataclasses import replace
import json
import math
from unittest import TestCase, main
from unittest.mock import patch

from skeleton.provider_environment import (
    BoundedRecordBuffer, DeterministicReplayBuffer, EnvironmentIdentity,
    EnvironmentMismatchError, ExactEnvironmentRegistry, HoldoutSplit,
    ReplayRecord, _canonical, _digest, make_record,
)
from skeleton.simulation import replay_checkpoint as checkpoint
from skeleton.simulation.fixed_tick import FixedTickReplay, InputEvent, ReplayError


class _MutableEnvironment:
    def __init__(self, simulation_id="world", seed=7):
        self.simulation_id = simulation_id
        self.seed = seed
        self._position = 0

    @property
    def state(self):
        return {"position": self._position}

    def reset(self):
        self._position = self.seed
        return self.state

    def step(self, action):
        self._position += action["dx"]
        return None


def _split_and_buffer(max_items=16):
    split = HoldoutSplit(salt="review-only-source-bound", holdout_fraction=0.25)
    return split, DeterministicReplayBuffer(
        split, max_items=max_items, max_bytes=256 * 1024,
    )


def _example_ids(split, count):
    index = 0
    found = []
    while len(found) < count:
        name = f"case-{index}"
        if not split.is_holdout(name):
            found.append(name)
        index += 1
    return found


def _replay():
    sequence = FixedTickReplay(seed=71)
    sequence.advance((InputEvent(1, "right", True),))
    sequence.advance((InputEvent(2, "interact", True),))
    return sequence


class BoundedEnvironmentEncodingTests(TestCase):
    def test_canonical_bytes_remain_backward_compatible(self):
        samples = [
            None,
            {"nested": [1, 2.25, True, None, "ää"], "z": {"a": "text"}},
            [["x", {"n": -23}], [0, 1]],
            (("alias", "table"), (2, 3)),
        ]
        for value in samples:
            with self.subTest(value=value):
                expected = json.dumps(
                    value, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False,
                ).encode("ascii")
                self.assertEqual(_canonical(value), expected)

    def test_nonstring_mapping_keys_are_rejected_at_all_depths(self):
        for value in (
            {1: "one"},
            {"nested": {True: "bool-key"}},
            {1: "old", "1": "new"},
            {"data": [{2.5: "float-key"}]},
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "string keys",
            ):
                _canonical(value)

    def test_non_json_values_and_nonfinite_floats_are_rejected(self):
        for value in (object(), {"x": object()}, {"x": math.inf},
                      {"x": math.nan}, {"x": -math.inf}):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                _canonical(value)

    def test_container_cycle_is_refused_by_depth_budget(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(ValueError, "depth budget"):
            _canonical(cycle)

    def test_large_nesting_is_refused_before_json_recursion(self):
        node: object = "x"
        for _ in range(34):
            node = [node]
        with self.assertRaisesRegex(ValueError, "depth budget"):
            _canonical(node)

    def test_exact_item_budget_is_not_silently_exceeded(self):
        with patch("skeleton.provider_environment.MAX_ENCODED_ITEMS", 10):
            with self.assertRaisesRegex(ValueError, "node budget"):
                _canonical(list(range(10)))
            self.assertEqual(json.loads(_canonical([1, 2])), [1, 2])

    def test_large_single_string_is_refused_before_serialization(self):
        with patch("skeleton.provider_environment.MAX_RECORD_BYTES", 128):
            with self.assertRaisesRegex(ValueError, "byte budget"):
                _canonical({"payload": "A" * 1000})

    def test_unicode_escaped_size_counts_against_byte_envelope(self):
        with patch("skeleton.provider_environment.MAX_RECORD_BYTES", 40):
            with self.assertRaisesRegex(ValueError, "byte bound"):
                _canonical({"name": "ø" * 30})

    def test_huge_integer_is_rejected_before_decimal_materialization(self):
        with self.assertRaisesRegex(ValueError, "numeric budget"):
            _canonical({"huge": 1 << 20000})

    def test_make_record_refuses_oversized_mapping_before_cloning(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        with patch("skeleton.provider_environment.MAX_ENCODED_ITEMS", 10):
            with self.assertRaisesRegex(ValueError, "element budget"):
                make_record("test", identity, {str(k): k for k in range(25)})

    def test_mutable_mapping_is_snapshotted_before_retention(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        split, buffer = _split_and_buffer()
        record_id = _example_ids(split, 1)[0]
        original = {"nested": {"values": [1, 2]}}
        record = make_record(record_id, identity, original)
        buffer.add(record)
        original["nested"]["values"].append(42)
        record.payload["nested"]["values"].append(43)
        self.assertEqual(
            buffer.records()[0].payload["nested"]["values"], [1, 2],
        )

    def test_streaming_digest_equals_original_canonical_record_list(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        split, buffer = _split_and_buffer(max_items=5)
        for index, case in enumerate(_example_ids(split, 12)):
            buffer.add(make_record(case, identity, {"index": index}))
        current = buffer.records()
        self.assertEqual(
            buffer.digest(),
            _digest([(r.example_id, r.payload_digest) for r in current]),
        )
        self.assertEqual(len(current), 5)
        self.assertEqual(buffer.evicted, 7)

    def test_sampling_is_reproducible_and_excludes_negative_seed(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        split, buffer = _split_and_buffer()
        for index, case in enumerate(_example_ids(split, 10)):
            buffer.add(make_record(case, identity, {"index": index}))
        self.assertEqual(buffer.sample(5, seed=13), buffer.sample(5, seed=13))
        with self.assertRaises(ValueError):
            buffer.sample(1, seed=-1)
        with self.assertRaises(ValueError):
            buffer.sample(1, seed=True)

    def test_internal_digest_does_not_deepcopy_payloads(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        split, buffer = _split_and_buffer()
        case = _example_ids(split, 1)[0]
        buffer.add(make_record(case, identity, {"value": 1}))
        # .digest() hashes immutable stored metadata, not user-visible clones.
        with patch.object(buffer, "_records_locked",
                          side_effect=AssertionError("deepcopy would break")):
            self.assertRegex(buffer.digest(), r"^[0-9a-f]{64}$")

    def test_registry_detects_adapter_mutation_after_registration(self):
        identity = EnvironmentIdentity("world", "source-v1", 7)
        registry = ExactEnvironmentRegistry()
        adapter = _MutableEnvironment()
        registry.register(identity, adapter)
        self.assertIs(registry.resolve(identity), adapter)
        adapter.seed = 9
        with self.assertRaisesRegex(EnvironmentMismatchError, "changed"):
            registry.resolve(identity)
        adapter.seed = 7
        adapter.simulation_id = "other-world"
        with self.assertRaisesRegex(EnvironmentMismatchError, "changed"):
            registry.resolve(identity)

    def test_registry_rejects_invalid_identity_and_boolean_seed(self):
        registry = ExactEnvironmentRegistry()
        with self.assertRaises(TypeError):
            registry.register("world", _MutableEnvironment())
        with self.assertRaises(TypeError):
            registry.resolve("world")
        with self.assertRaises(EnvironmentMismatchError):
            registry.register(
                EnvironmentIdentity("world", "source-v1", 1),
                _MutableEnvironment(seed=True),
            )


class CheckpointCodecTests(TestCase):
    def test_streaming_output_matches_legacy_sorted_json_byte_for_byte(self):
        replay = _replay()
        frames = [
            {
                "tick": f.tick, "prior": f.prior_digest, "digest": f.digest,
                "events": [
                    {"tick": e.tick, "action": e.action, "pressed": e.pressed}
                    for e in f.events
                ],
            }
            for f in replay.frames
        ]
        legacy = json.dumps({
            "schema": checkpoint.SCHEMA, "hz": replay.hz,
            "seed": replay.seed, "head": replay.digest, "frames": frames,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        self.assertEqual(checkpoint.encode(replay), legacy)
        self.assertEqual(checkpoint.decode(legacy).frames, replay.frames)

    def test_duplicate_keys_are_rejected_at_top_level(self):
        encoded = checkpoint.encode(_replay())
        forged = encoded[:-1] + b',"head":"0"}'
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            checkpoint.decode(forged)

    def test_duplicate_keys_in_event_are_rejected_before_replay(self):
        encoded = checkpoint.encode(_replay())
        needle = b'"action":"right"'
        self.assertEqual(encoded.count(needle), 1)
        forged = encoded.replace(
            needle, b'"action":"right","action":"left"', 1,
        )
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            checkpoint.decode(forged)

    def test_duplicate_keys_in_frame_are_rejected(self):
        encoded = checkpoint.encode(_replay())
        needle = b'"prior":"'
        self.assertGreaterEqual(encoded.count(needle), 1)
        forged = encoded.replace(
            needle, b'"tick":1,"prior":"', 1,
        )
        with self.assertRaisesRegex(ReplayError, "duplicate"):
            checkpoint.decode(forged)

    def test_nonfinite_constants_are_rejected_before_shape_admission(self):
        encoded = checkpoint.encode(_replay())
        forged = encoded[:-1] + b',"ignored":NaN}'
        with self.assertRaisesRegex(ReplayError, "non-finite"):
            checkpoint.decode(forged)

    def test_oversized_output_is_refused_before_full_serialization(self):
        replay = _replay()
        with patch.object(checkpoint, "MAX_CHECKPOINT_BYTES", 220):
            with self.assertRaisesRegex(ReplayError, "byte budget"):
                checkpoint.encode(replay)

    def test_tampered_frame_cannot_be_encoded_as_valid_checkpoint(self):
        replay = _replay()
        replay._frames[0] = replace(replay.frames[0], digest="0" * 64)
        with self.assertRaises(ReplayError):
            checkpoint.encode(replay)

    def test_tampered_head_cannot_be_encoded_as_valid_checkpoint(self):
        replay = _replay()
        replay._head = "0" * 64
        with self.assertRaisesRegex(ReplayError, "divergence"):
            checkpoint.encode(replay)

    def test_duplicate_input_rejection_does_not_mutate_replay(self):
        replay = _replay()
        bytes_before = checkpoint.encode(replay)
        forged = bytes_before[:-1] + b',"head":"0"}'
        with self.assertRaises(ReplayError):
            checkpoint.decode(forged)
        self.assertEqual(checkpoint.encode(replay), bytes_before)

    def test_nonbytes_encoding_and_malformed_source_fail_closed(self):
        for value in (None, "not bytes", {}, bytearray(b"{}")):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ReplayError):
                    checkpoint.decode(value)
        with self.assertRaises(ReplayError):
            checkpoint.encode(object())


if __name__ == "__main__":
    main()
