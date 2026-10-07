"""GB-20 load path residual / conservation / stress."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.law import MAX_LOAD_N, SEGMENT_N, VERTEBRA_N
from skeleton.spine.load_path import (
    assert_segment_count,
    build_axial_path,
    build_eccentric_path,
    is_conserved,
    load_card_payload,
    peak_axial,
    peak_moment,
    safety_factor,
    shear_components,
)
from skeleton.spine.stress import (
    all_disc_stresses,
    body_stress,
    mean_disc_pressure,
    nachemson_estimate,
    pressure_profile,
    stress_ok,
    worst_disc,
)


class TestLoadResidual(unittest.TestCase):
    def test_conserved_without_body_weight(self) -> None:
        chain = default_chain()
        path = build_axial_path(chain, cranial_fz=100.0, include_body_weights=False)
        self.assertTrue(is_conserved(path))
        self.assertLessEqual(path.residual(), 1e-6)
        self.assertEqual(len(path.stations), VERTEBRA_N)
        self.assertEqual(len(path.segment_loads), SEGMENT_N)
        assert_segment_count(path)

    def test_body_weight_residual_still_zero(self) -> None:
        chain = default_chain()
        path = build_axial_path(chain, cranial_fz=100.0, include_body_weights=True)
        self.assertLessEqual(path.residual(), 1e-6)
        self.assertGreater(peak_axial(path), 100.0)

    def test_peak_and_safety(self) -> None:
        path = build_axial_path(default_chain(), cranial_fz=200.0, include_body_weights=False)
        self.assertAlmostEqual(peak_axial(path), 200.0, places=6)
        self.assertGreater(safety_factor(path), 1.0)

    def test_load_ceiling(self) -> None:
        chain = default_chain()
        with self.assertRaises(ValueError):
            build_axial_path(chain, cranial_fz=MAX_LOAD_N + 1)

    def test_eccentric_moment(self) -> None:
        chain = default_chain()
        path = build_eccentric_path(chain, cranial_fz=100.0, lever_mm=50.0)
        self.assertGreater(peak_moment(path), 0.0)
        self.assertLessEqual(path.residual(), 1e-6)

    def test_shear_zero_axial(self) -> None:
        path = build_axial_path(default_chain(), include_body_weights=False)
        self.assertTrue(all(s == 0.0 for s in shear_components(path)))

    def test_card_payload(self) -> None:
        path = build_axial_path(default_chain())
        card = load_card_payload(path)
        for k in ("peak_axial", "peak_moment", "residual", "safety", "n_stations"):
            self.assertIn(k, card)

    def test_stress_pipeline(self) -> None:
        chain = default_chain()
        path = build_axial_path(chain, cranial_fz=150.0)
        discs = all_disc_stresses(chain, path)
        self.assertEqual(len(discs), SEGMENT_N)
        self.assertIsInstance(stress_ok(chain, path), bool)
        self.assertIsNotNone(worst_disc(discs))
        self.assertGreaterEqual(mean_disc_pressure(chain, path), 0.0)
        self.assertEqual(len(pressure_profile(chain, path)), SEGMENT_N)
        bs = body_stress(chain, path)
        self.assertEqual(len(bs), VERTEBRA_N)
        self.assertGreater(nachemson_estimate(700.0, "standing"), 0.0)


if __name__ == "__main__":
    unittest.main()
