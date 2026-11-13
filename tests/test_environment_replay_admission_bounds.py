"""GF-P0 environment replay hostile-record and bounded-route regression."""
import unittest

from skeleton.provider_environment import (
    DeterministicReplayBuffer, EnvironmentIdentity, HoldoutBuffer,
    HoldoutSplit, ReplayRecord, make_record, route_records,
)


class EnvironmentBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.split = HoldoutSplit(salt="source-review", holdout_fraction=0.25)
        self.environment = EnvironmentIdentity("scene_1", "model_sha256", 7)
        self.replay = DeterministicReplayBuffer(self.split, max_items=4)
        self.holdout = HoldoutBuffer(self.split, max_items=4)

    def test_unsafe_record_metadata_is_never_admitted(self):
        key = next(f"rec-{i}" for i in range(100) if not self.split.is_holdout(f"rec-{i}"))
        valid = make_record(key, self.environment, {"payload": [1, 2]})
        cases = (
            ReplayRecord(valid.example_id, valid.environment_key, "x", valid.payload),
            ReplayRecord(valid.example_id, valid.environment_key, "A" * 64, valid.payload),
            ReplayRecord(valid.example_id, valid.environment_key, valid.payload_digest, None),
            ReplayRecord(valid.example_id, "", valid.payload_digest, valid.payload),
            ReplayRecord("", valid.environment_key, valid.payload_digest, valid.payload),
        )
        for forged in cases:
            with self.subTest(forged=repr(forged)), self.assertRaises(ValueError):
                self.replay.add(forged)
        self.assertEqual(len(self.replay), 0)

    def test_non_records_are_rejected_without_partial_append(self):
        for invalid in (None, [], {}, 0):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                self.replay.add(invalid)
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                self.holdout.add(invalid)
        self.assertEqual(len(self.replay), 0)
        self.assertEqual(len(self.holdout), 0)

    def test_route_rejects_unbounded_iterable(self):
        valid = make_record("r0", self.environment, {"v": 0})
        with self.assertRaisesRegex(ValueError, "bounded admission"):
            route_records((valid for _ in range(100001)), self.replay, self.holdout)
        self.assertLessEqual(len(self.replay) + len(self.holdout), 8)


if __name__ == "__main__":
    unittest.main()
