"""GB-20 deep per-posture and per-motion checks."""

from __future__ import annotations

import unittest

from skeleton.spine.articulation import all_rom_ok, rom_violations
from skeleton.spine.chain import assert_chain_integrity, default_chain
from skeleton.spine.compare import diff_chains, similarity
from skeleton.spine.digest import chain_digest, digest_drift
from skeleton.spine.invariant import check_all
from skeleton.spine.kinematics import end_effector, forward_frames, path_length_mm
from skeleton.spine.law import VERTEBRA_N
from skeleton.spine.load_path import build_axial_path
from skeleton.spine.metrics import compute_metrics, metrics_hit
from skeleton.spine.motion import library, sample_timeline, validate_library_rom
from skeleton.spine.posture import BUILDERS, blend_postures, build_posture, list_postures
from skeleton.spine.serialize import chain_from_dict, chain_to_dict, roundtrip_ok
from skeleton.spine.stability import stability_report
from skeleton.spine.stiffness import chain_energy


class TestEveryPostureDeep(unittest.TestCase):

    def test_posture_neutral_bundle(self) -> None:
        base = default_chain()
        p = build_posture("neutral", base)
        self.assertEqual(p.name, "neutral")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_flexion_30_bundle(self) -> None:
        base = default_chain()
        p = build_posture("flexion_30", base)
        self.assertEqual(p.name, "flexion_30")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_flexion_60_bundle(self) -> None:
        base = default_chain()
        p = build_posture("flexion_60", base)
        self.assertEqual(p.name, "flexion_60")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_extension_20_bundle(self) -> None:
        base = default_chain()
        p = build_posture("extension_20", base)
        self.assertEqual(p.name, "extension_20")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_lateral_right_15_bundle(self) -> None:
        base = default_chain()
        p = build_posture("lateral_right_15", base)
        self.assertEqual(p.name, "lateral_right_15")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_lateral_left_15_bundle(self) -> None:
        base = default_chain()
        p = build_posture("lateral_left_15", base)
        self.assertEqual(p.name, "lateral_left_15")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_axial_cw_10_bundle(self) -> None:
        base = default_chain()
        p = build_posture("axial_cw_10", base)
        self.assertEqual(p.name, "axial_cw_10")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_axial_ccw_10_bundle(self) -> None:
        base = default_chain()
        p = build_posture("axial_ccw_10", base)
        self.assertEqual(p.name, "axial_ccw_10")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_sitting_bundle(self) -> None:
        base = default_chain()
        p = build_posture("sitting", base)
        self.assertEqual(p.name, "sitting")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_posture_forward_bend_bundle(self) -> None:
        base = default_chain()
        p = build_posture("forward_bend", base)
        self.assertEqual(p.name, "forward_bend")
        self.assertEqual(len(p.vertebrae), VERTEBRA_N)
        assert_chain_integrity(p)
        self.assertTrue(all_rom_ok(p.segments), rom_violations(p.segments))
        self.assertEqual(check_all(p), [])
        self.assertTrue(roundtrip_ok(p))
        restored = chain_from_dict(chain_to_dict(p))
        self.assertEqual(chain_digest(p), chain_digest(restored))
        frames = forward_frames(p)
        self.assertEqual(len(frames), VERTEBRA_N)
        tip = end_effector(p)
        self.assertIsInstance(tip.z, float)
        self.assertGreater(path_length_mm(p), 0.0)
        path = build_axial_path(p, cranial_fz=80.0, include_body_weights=False)
        self.assertLessEqual(path.residual(), 1e-6)
        m = compute_metrics(p)
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(m["vertebra_n"], VERTEBRA_N)
        if p.name == "neutral":
            self.assertEqual(metrics_hit(m), 1)
        energy = chain_energy(p.segments)
        self.assertGreaterEqual(energy, 0.0)
        stab = stability_report(p, applied_n=50.0)
        self.assertIsNotNone(stab.margin)

    def test_all_builders_registered(self) -> None:
        self.assertEqual(set(list_postures()), set(BUILDERS))


class TestPosturePairs(unittest.TestCase):

    def test_pair_neutral_vs_flexion_30(self) -> None:
        base = default_chain()
        ca = build_posture("neutral", base)
        cb = build_posture("flexion_30", base)
        if "neutral" == "flexion_30":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_neutral_vs_flexion_60(self) -> None:
        base = default_chain()
        ca = build_posture("neutral", base)
        cb = build_posture("flexion_60", base)
        if "neutral" == "flexion_60":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_neutral_vs_extension_20(self) -> None:
        base = default_chain()
        ca = build_posture("neutral", base)
        cb = build_posture("extension_20", base)
        if "neutral" == "extension_20":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_neutral_vs_sitting(self) -> None:
        base = default_chain()
        ca = build_posture("neutral", base)
        cb = build_posture("sitting", base)
        if "neutral" == "sitting":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_flexion_30_vs_flexion_60(self) -> None:
        base = default_chain()
        ca = build_posture("flexion_30", base)
        cb = build_posture("flexion_60", base)
        if "flexion_30" == "flexion_60":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_lateral_left_15_vs_lateral_right_15(self) -> None:
        base = default_chain()
        ca = build_posture("lateral_left_15", base)
        cb = build_posture("lateral_right_15", base)
        if "lateral_left_15" == "lateral_right_15":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_axial_cw_10_vs_axial_ccw_10(self) -> None:
        base = default_chain()
        ca = build_posture("axial_cw_10", base)
        cb = build_posture("axial_ccw_10", base)
        if "axial_cw_10" == "axial_ccw_10":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_sitting_vs_forward_bend(self) -> None:
        base = default_chain()
        ca = build_posture("sitting", base)
        cb = build_posture("forward_bend", base)
        if "sitting" == "forward_bend":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_neutral_vs_forward_bend(self) -> None:
        base = default_chain()
        ca = build_posture("neutral", base)
        cb = build_posture("forward_bend", base)
        if "neutral" == "forward_bend":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

    def test_pair_extension_20_vs_flexion_30(self) -> None:
        base = default_chain()
        ca = build_posture("extension_20", base)
        cb = build_posture("flexion_30", base)
        if "extension_20" == "flexion_30":
            self.assertAlmostEqual(similarity(ca, cb), 1.0)
        else:
            self.assertLess(similarity(ca, cb), 1.0)
            diff = diff_chains(ca, cb)
            self.assertGreaterEqual(diff.digest_hamming, 0)
        mid = blend_postures(ca, cb, 0.35)
        self.assertTrue(all_rom_ok(mid.segments))
        self.assertEqual(len(mid.vertebrae), VERTEBRA_N)
        # drift vs self is zero
        self.assertEqual(digest_drift(ca, ca), 0)

class TestMotionDeep(unittest.TestCase):
    def test_library_rom_map(self) -> None:
        result = validate_library_rom()
        for name, ok in result.items():
            self.assertTrue(ok, name)


    def test_each_clip_timeline(self) -> None:
        lib = library()
        self.assertTrue(lib)
        for name, clip in lib.items():
            samples = sample_timeline(clip, fps=3.0)
            self.assertGreater(len(samples), 0, name)
            for t, chain in samples:
                self.assertEqual(len(chain.vertebrae), VERTEBRA_N)
                self.assertTrue(all_rom_ok(chain.segments), f"{name}@{t}")
                assert_chain_integrity(chain)


if __name__ == "__main__":
    unittest.main()
