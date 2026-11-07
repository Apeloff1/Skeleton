"""GB-20 serialize/compare matrix across postures and loads."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.compare import diff_chains, report, same_topology, similarity
from skeleton.spine.digest import chain_digest, digests_equal
from skeleton.spine.load_path import build_axial_path, is_conserved
from skeleton.spine.posture import build_posture, list_postures
from skeleton.spine.serialize import chain_from_dict, chain_to_dict, roundtrip_ok


class TestSerializeCompareMatrix(unittest.TestCase):

    def test_roundtrip_neutral(self) -> None:
        chain = build_posture("neutral")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_flexion_30(self) -> None:
        chain = build_posture("flexion_30")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_flexion_60(self) -> None:
        chain = build_posture("flexion_60")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_extension_20(self) -> None:
        chain = build_posture("extension_20")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_sitting(self) -> None:
        chain = build_posture("sitting")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_forward_bend(self) -> None:
        chain = build_posture("forward_bend")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_lateral_right_15(self) -> None:
        chain = build_posture("lateral_right_15")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_lateral_left_15(self) -> None:
        chain = build_posture("lateral_left_15")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_axial_cw_10(self) -> None:
        chain = build_posture("axial_cw_10")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_roundtrip_axial_ccw_10(self) -> None:
        chain = build_posture("axial_ccw_10")
        self.assertTrue(roundtrip_ok(chain))
        restored = chain_from_dict(chain_to_dict(chain))
        self.assertTrue(digests_equal(chain, restored))
        self.assertTrue(same_topology(chain, restored))
        self.assertAlmostEqual(similarity(chain, restored), 1.0, places=9)

    def test_compare_neutral__neutral(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("neutral")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "neutral":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__flexion_30(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("flexion_30")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "flexion_30":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__flexion_60(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("flexion_60")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "flexion_60":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__extension_20(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("extension_20")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "extension_20":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__sitting(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("sitting")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "sitting":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__forward_bend(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "forward_bend":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__lateral_right_15(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__lateral_left_15(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__axial_cw_10(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_neutral__axial_ccw_10(self) -> None:
        ca = build_posture("neutral")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "neutral" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__flexion_30(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("flexion_30")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "flexion_30":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__flexion_60(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("flexion_60")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "flexion_60":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__extension_20(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("extension_20")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "extension_20":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__sitting(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("sitting")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "sitting":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__forward_bend(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "forward_bend":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__lateral_right_15(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__lateral_left_15(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__axial_cw_10(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_30__axial_ccw_10(self) -> None:
        ca = build_posture("flexion_30")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_30" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__flexion_60(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("flexion_60")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "flexion_60":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__extension_20(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("extension_20")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "extension_20":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__sitting(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("sitting")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "sitting":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__forward_bend(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        # same relatives; digest differs only by chain.name
        self.assertAlmostEqual(similarity(ca, cb), 1.0, places=9)
        self.assertEqual(
            [s.relative.as_tuple() for s in ca.segments],
            [s.relative.as_tuple() for s in cb.segments],
        )

    def test_compare_flexion_60__lateral_right_15(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__lateral_left_15(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__axial_cw_10(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_flexion_60__axial_ccw_10(self) -> None:
        ca = build_posture("flexion_60")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "flexion_60" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__extension_20(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("extension_20")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "extension_20":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__sitting(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("sitting")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "sitting":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__forward_bend(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "forward_bend":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__lateral_right_15(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__lateral_left_15(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__axial_cw_10(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_extension_20__axial_ccw_10(self) -> None:
        ca = build_posture("extension_20")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "extension_20" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__sitting(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("sitting")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "sitting":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__forward_bend(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "forward_bend":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__lateral_right_15(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__lateral_left_15(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__axial_cw_10(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_sitting__axial_ccw_10(self) -> None:
        ca = build_posture("sitting")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "sitting" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_forward_bend__forward_bend(self) -> None:
        ca = build_posture("forward_bend")
        cb = build_posture("forward_bend")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "forward_bend" == "forward_bend":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_forward_bend__lateral_right_15(self) -> None:
        ca = build_posture("forward_bend")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "forward_bend" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_forward_bend__lateral_left_15(self) -> None:
        ca = build_posture("forward_bend")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "forward_bend" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_forward_bend__axial_cw_10(self) -> None:
        ca = build_posture("forward_bend")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "forward_bend" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_forward_bend__axial_ccw_10(self) -> None:
        ca = build_posture("forward_bend")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "forward_bend" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_right_15__lateral_right_15(self) -> None:
        ca = build_posture("lateral_right_15")
        cb = build_posture("lateral_right_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_right_15" == "lateral_right_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_right_15__lateral_left_15(self) -> None:
        ca = build_posture("lateral_right_15")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_right_15" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_right_15__axial_cw_10(self) -> None:
        ca = build_posture("lateral_right_15")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_right_15" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_right_15__axial_ccw_10(self) -> None:
        ca = build_posture("lateral_right_15")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_right_15" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_left_15__lateral_left_15(self) -> None:
        ca = build_posture("lateral_left_15")
        cb = build_posture("lateral_left_15")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_left_15" == "lateral_left_15":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_left_15__axial_cw_10(self) -> None:
        ca = build_posture("lateral_left_15")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_left_15" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_lateral_left_15__axial_ccw_10(self) -> None:
        ca = build_posture("lateral_left_15")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "lateral_left_15" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_axial_cw_10__axial_cw_10(self) -> None:
        ca = build_posture("axial_cw_10")
        cb = build_posture("axial_cw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "axial_cw_10" == "axial_cw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_axial_cw_10__axial_ccw_10(self) -> None:
        ca = build_posture("axial_cw_10")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "axial_cw_10" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

    def test_compare_axial_ccw_10__axial_ccw_10(self) -> None:
        ca = build_posture("axial_ccw_10")
        cb = build_posture("axial_ccw_10")
        self.assertTrue(same_topology(ca, cb))
        sim = similarity(ca, cb)
        if "axial_ccw_10" == "axial_ccw_10":
            self.assertAlmostEqual(sim, 1.0, places=9)
            self.assertEqual(chain_digest(ca), chain_digest(cb))
        else:
            self.assertLess(sim, 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.pose_l2, 0.0)
            r = report(ca, cb)
            self.assertEqual(r["same_topology"], 1)

class TestLoadMatrix(unittest.TestCase):

    def test_axial_conserved_fz_0(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=0.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_25(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=25.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_50(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=50.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_100(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=100.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_200(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=200.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_400(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=400.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_800(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=800.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_axial_conserved_fz_1200(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=1200.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)

    def test_posture_list_stable(self) -> None:
        self.assertEqual(list_postures(), list_postures())


if __name__ == "__main__":
    unittest.main()
