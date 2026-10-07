"""GB-20 serialize roundtrip and compare divergence."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.compare import (
    ChainDiff,
    changed_segment_labels,
    diff_chains,
    metric_delta,
    report,
    same_topology,
    segment_pose_distance,
    similarity,
)
from skeleton.spine.digest import chain_digest, digests_equal
from skeleton.spine.posture import build_posture
from skeleton.spine.serialize import (
    chain_from_dict,
    chain_to_dict,
    compact_relatives,
    pose_from_dict,
    pose_to_dict,
    roundtrip_ok,
    segment_to_dict,
    vertebra_to_dict,
)
from skeleton.spine.vertebra import Pose6, ZERO_POSE


class TestSerializeRoundtrip(unittest.TestCase):
    def test_roundtrip_ok_helper(self) -> None:
        self.assertTrue(roundtrip_ok())
        self.assertTrue(roundtrip_ok(default_chain()))

    def test_dict_roundtrip_preserves_digest(self) -> None:
        chain = default_chain()
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertEqual(chain.labels(), restored.labels())
        self.assertTrue(same_topology(chain, restored))

    def test_posture_roundtrip(self) -> None:
        flexed = build_posture("flexion_30")
        restored = chain_from_dict(chain_to_dict(flexed))
        self.assertEqual(chain_digest(flexed), chain_digest(restored))

    def test_pose_dict(self) -> None:
        p = Pose6(rx=1.0, ry=-2.0, rz=0.5)
        self.assertEqual(pose_from_dict(pose_to_dict(p)).as_tuple(), p.as_tuple())
        self.assertEqual(pose_from_dict(pose_to_dict(ZERO_POSE)).as_tuple(), ZERO_POSE.as_tuple())

    def test_vertebra_segment_dicts(self) -> None:
        chain = default_chain()
        vd = vertebra_to_dict(chain.vertebrae[0])
        self.assertIn("label", vd)
        sd = segment_to_dict(chain.segments[0])
        self.assertIn("label", sd)

    def test_compact_relatives(self) -> None:
        rel = compact_relatives(default_chain())
        self.assertEqual(len(rel), len(default_chain().segments))


class TestCompareDivergence(unittest.TestCase):
    def test_identical_similarity_one(self) -> None:
        a = default_chain()
        b = default_chain()
        self.assertAlmostEqual(similarity(a, b), 1.0, places=9)
        self.assertEqual(segment_pose_distance(a, b), 0.0)
        self.assertEqual(changed_segment_labels(a, b), [])
        self.assertTrue(same_topology(a, b))

    def test_flexion_diverges(self) -> None:
        a = default_chain()
        b = build_posture("flexion_30", a)
        diff = diff_chains(a, b)
        self.assertIsInstance(diff, ChainDiff)
        self.assertGreater(diff.pose_l2, 0.0)
        self.assertGreater(diff.tip_delta_mm, 0.0)
        self.assertGreater(diff.digest_hamming, 0)
        self.assertGreater(len(diff.changed_segments), 0)
        self.assertLess(similarity(a, b), 1.0)
        self.assertTrue(same_topology(a, b))

    def test_report_keys(self) -> None:
        a = default_chain()
        b = build_posture("sitting", a)
        r = report(a, b)
        for k in ("pose_l2", "similarity", "same_topology", "digest_a", "digest_b"):
            self.assertIn(k, r)

    def test_metric_delta(self) -> None:
        a = default_chain()
        b = build_posture("flexion_60", a)
        delta = metric_delta(a, b)
        self.assertIsInstance(delta, dict)
        self.assertTrue(any(abs(v) > 0 for v in delta.values()))


if __name__ == "__main__":
    unittest.main()
