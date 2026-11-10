"""GF-P0 strict replay admission: bounded shape, generation and holdout custody.

The tests use real records and buffer APIs; no external provider/network access.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.provider_environment import (
    MAX_ENCODED_ITEMS,
    MAX_PAYLOAD_DEPTH,
    MAX_RECORD_BYTES,
    DeterministicReplayBuffer,
    EnvironmentIdentity,
    ExactEnvironmentRegistry,
    HoldoutBuffer,
    HoldoutSplit,
    ReplayRecord,
    _canonical,
    _digest,
    _index_digest,
    make_record,
    route_records,
)


IDENTITY = EnvironmentIdentity("test-arena", "build-source-1", 99)


def training_key(split: HoldoutSplit) -> str:
    return next(
        f"candidate-{i}" for i in range(1000)
        if not split.is_holdout(f"candidate-{i}")
    )


class StrictReplayEnvelopeTests(unittest.TestCase):
    def test_scalar_and_nested_round_trip_remain_canonical(self) -> None:
        source = {
            "z": [{"item": "灯", "enabled": True, "count": 2}],
            "a": {"flags": [None, False, 0, 1.25]},
        }
        encoded = _canonical(source)
        self.assertLessEqual(len(encoded), MAX_RECORD_BYTES)
        self.assertEqual(encoded, _canonical(source))
        self.assertEqual(
            __import__("json").loads(encoded), source,
        )

    def test_json_ambiguous_keys_are_rejected_at_all_depths(self) -> None:
        for value in (
            {1: "integer alias", "1": "string alias"},
            {True: "bool alias"},
            {"nested": [{1: "scalar"}]},
            {"nested": {None: "none"}},
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "keys"):
                    _canonical(value)

    def test_cyclic_graph_fails_before_encoder_loop(self) -> None:
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(ValueError, "cyclic"):
            _canonical({"nested": cycle})
        mapping = {}
        mapping["self"] = mapping
        with self.assertRaisesRegex(ValueError, "cyclic"):
            _canonical(mapping)

    def test_shared_noncyclic_graph_remains_legal(self) -> None:
        shared = {"items": [1, 2]}
        encoded = _canonical({"left": shared, "right": shared})
        self.assertEqual(
            __import__("json").loads(encoded)["left"],
            __import__("json").loads(encoded)["right"],
        )

    def test_nesting_and_item_limits_fail_early(self) -> None:
        deep = 0
        for _ in range(MAX_PAYLOAD_DEPTH + 3):
            deep = [deep]
        with self.assertRaisesRegex(ValueError, "depth"):
            _canonical(deep)
        with self.assertRaisesRegex(ValueError, "item budget"):
            _canonical([0] * (MAX_ENCODED_ITEMS + 1))

    def test_generator_and_custom_objects_cannot_enter_replay(self) -> None:
        for value in (object(), iter([1, 2]), {1, 2}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ValueError):
                    _canonical({"bad": value})

    def test_invalid_floats_refused_without_partial_record(self) -> None:
        split = HoldoutSplit(salt="semantic-immutability", holdout_fraction=0.2)
        replay = DeterministicReplayBuffer(split, max_items=8)
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    make_record("bad", IDENTITY, {"value": value})
        self.assertEqual(len(replay), 0)

    def test_large_scalar_does_not_pass_budget(self) -> None:
        with self.assertRaises(ValueError):
            _canonical({"oversized": "x" * (MAX_RECORD_BYTES + 1)})
        with patch("skeleton.provider_environment.MAX_RECORD_BYTES", 64):
            with self.assertRaises(ValueError):
                _canonical({"string": "y" * 80})

    def test_encoder_does_not_invoke_monolithic_json_dumps(self) -> None:
        with patch(
            "skeleton.provider_environment.json.dumps",
            side_effect=AssertionError("monolithic encoder is prohibited"),
        ):
            payload = _canonical({"a": [1, 2, 3], "z": "safe"})
        self.assertEqual(payload, b'{"a":[1,2,3],"z":"safe"}')

    def test_missing_registry_identity_is_value_error(self) -> None:
        registry = ExactEnvironmentRegistry()
        with self.assertRaisesRegex(ValueError, "identity"):
            registry.register(None, object())


class AtomicSampleGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.split = HoldoutSplit(salt="same-record-generation", holdout_fraction=0.2)
        self.replay = DeterministicReplayBuffer(self.split, max_items=64)
        self.holdout = HoldoutBuffer(self.split, max_items=64)
        self.ident = IDENTITY

    def populate(self) -> None:
        route_records(
            [
                make_record(f"r-{i}", self.ident, {"index": i, "sequence": [i, i + 1]})
                for i in range(60)
            ],
            self.replay,
            self.holdout,
        )

    def test_sampling_uses_one_generation_and_never_re_reads_digest(self) -> None:
        self.populate()
        first = self.replay.sample(12, seed=1)
        with patch.object(
            self.replay, "digest",
            side_effect=AssertionError("cannot reread a newer generation"),
        ):
            second = self.replay.sample(12, seed=1)
        self.assertEqual(first, second)

    def test_large_buffer_index_has_no_1mib_digest_cliff(self) -> None:
        # 6,000 allowed 240-character identities are larger than the 1 MiB
        # per-record JSON budget when combined into a single index array.
        rows = tuple(
            ReplayRecord(
                f"{i:06d}-" + ("a" * 233),
                "environment",
                "b" * 64,
                {"i": i},
            )
            for i in range(6000)
        )
        result = _index_digest(rows)
        self.assertEqual(len(result), 64)
        self.assertEqual(result, _index_digest(iter(rows)))
        with self.assertRaises(ValueError):
            _digest([(r.example_id, r.payload_digest) for r in rows])

    def test_streamed_index_hash_matches_legacy_for_small_buffers(self) -> None:
        self.populate()
        rows = self.replay.records()
        expected = _digest([(r.example_id, r.payload_digest) for r in rows])
        self.assertEqual(_index_digest(rows), expected)
        self.assertEqual(self.replay.digest(), expected)

    def test_sampling_cannot_mutate_retained_payload(self) -> None:
        self.populate()
        sampled = self.replay.sample(1, seed=0)[0]
        sampled.payload["sequence"][0] = 123456
        retained = self.replay.records()
        match = next(r for r in retained if r.example_id == sampled.example_id)
        self.assertNotEqual(match.payload["sequence"][0], 123456)

    def test_buffer_rejects_post_insert_digest_forgery(self) -> None:
        key = training_key(self.split)
        record = make_record(key, self.ident, {"nested": {"safe": True}})
        forged = ReplayRecord(
            record.example_id, record.environment_key,
            record.payload_digest, {"nested": {"safe": False}},
        )
        with self.assertRaisesRegex(ValueError, "digest"):
            self.replay.add(forged)
        self.assertEqual(len(self.replay), 0)

    def test_buffer_retained_bytes_are_bounded_after_eviction(self) -> None:
        self.populate()
        self.assertLessEqual(self.replay.retained_bytes, self.replay.max_bytes)
        self.assertLessEqual(self.holdout.retained_bytes, self.holdout.max_bytes)
        self.assertLessEqual(len(self.replay), self.replay.max_items)
        self.assertLessEqual(len(self.holdout), self.holdout.max_items)


if __name__ == "__main__":
    unittest.main()
