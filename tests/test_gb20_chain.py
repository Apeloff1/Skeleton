"""GB-20 chain integrity and vertebra/segment wiring."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import (
    SpineChain,
    assert_chain_integrity,
    chain_height_mm,
    default_chain,
    rebind_segments,
)
from skeleton.spine.law import SEGMENT_N, VERTEBRA_N
from skeleton.spine.segment import build_segments, mobile_segments, segment_by_label
from skeleton.spine.taxonomy import Region, all_labels
from skeleton.spine.vertebra import Pose6, ZERO_POSE, default_column, mean_pose


class TestChainIntegrity(unittest.TestCase):
    def test_default_counts(self) -> None:
        chain = default_chain()
        self.assertEqual(len(chain.vertebrae), VERTEBRA_N)
        self.assertEqual(len(chain.segments), SEGMENT_N)
        self.assertEqual(len(chain), VERTEBRA_N)
        assert_chain_integrity(chain)

    def test_segment_cranial_caudal_match(self) -> None:
        chain = default_chain()
        for i, seg in enumerate(chain.segments):
            self.assertEqual(seg.sid.cranial, chain.vertebrae[i].label)
            self.assertEqual(seg.sid.caudal, chain.vertebrae[i + 1].label)
            self.assertEqual(seg.sid.index, i)

    def test_labels_unique_ordered(self) -> None:
        chain = default_chain()
        self.assertEqual(chain.labels(), all_labels())
        self.assertEqual(len(set(chain.labels())), VERTEBRA_N)

    def test_cranial_caudal_accessors(self) -> None:
        chain = default_chain()
        self.assertEqual(chain.cranial().label, all_labels()[0])
        self.assertEqual(chain.caudal().label, all_labels()[-1])

    def test_region_filter(self) -> None:
        chain = default_chain()
        cerv = chain.region(Region.CERVICAL)
        self.assertEqual(len(cerv), 7)
        self.assertTrue(all(v.region is Region.CERVICAL for v in cerv))

    def test_with_poses_energy(self) -> None:
        chain = default_chain()
        self.assertEqual(chain.energy(), 0.0)
        posed = chain.with_poses({chain.vertebrae[0].label: Pose6(rx=1.0)})
        self.assertGreater(posed.energy(), 0.0)
        self.assertEqual(chain.energy(), 0.0)  # immutable

    def test_height_positive(self) -> None:
        chain = default_chain()
        self.assertGreater(chain_height_mm(chain), 500.0)

    def test_mobile_segment_count(self) -> None:
        chain = default_chain()
        self.assertEqual(chain.mobile_segment_count(), len(mobile_segments(chain.segments)))
        self.assertGreater(chain.mobile_segment_count(), 0)

    def test_rebind_preserves_topology(self) -> None:
        chain = default_chain()
        rebound = rebind_segments(chain, chain.segments)
        self.assertEqual(rebound.labels(), chain.labels())
        assert_chain_integrity(rebound)

    def test_slice_ordinals(self) -> None:
        chain = default_chain()
        mid = chain.slice_ordinals(5, 10)
        self.assertEqual(len(mid), 6)

    def test_mean_pose_zero_default(self) -> None:
        chain = default_chain()
        mp = chain.mean_pose()
        self.assertEqual(mp.as_tuple(), ZERO_POSE.as_tuple())

    def test_junctions_nonempty(self) -> None:
        chain = default_chain()
        self.assertGreaterEqual(len(chain.junctions()), 4)

    def test_build_from_column(self) -> None:
        col = default_column()
        segs = build_segments(col)
        chain = SpineChain(vertebrae=col, segments=segs, name="manual")
        assert_chain_integrity(chain)
        self.assertEqual(chain.name, "manual")

    def test_bad_counts_raise(self) -> None:
        chain = default_chain()
        with self.assertRaises(ValueError):
            SpineChain(vertebrae=chain.vertebrae[:10], segments=chain.segments[:9])

    def test_get_by_label(self) -> None:
        chain = default_chain()
        lb = chain.labels()[3]
        self.assertEqual(chain.get(lb).label, lb)

    def test_segment_by_label(self) -> None:
        chain = default_chain()
        seg = chain.segments[0]
        self.assertEqual(segment_by_label(chain.segments)[seg.label].label, seg.label)

    def test_with_name(self) -> None:
        chain = default_chain().with_name("renamed")
        self.assertEqual(chain.name, "renamed")

    def test_iteration(self) -> None:
        chain = default_chain()
        labels = [v.label for v in chain]
        self.assertEqual(labels, chain.labels())


def region_ok(v) -> bool:
    return True


if __name__ == "__main__":
    unittest.main()
