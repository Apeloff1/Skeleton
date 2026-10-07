"""GB-20 posture builders, blending, motion library."""

from __future__ import annotations

import unittest

from skeleton.spine.articulation import all_rom_ok
from skeleton.spine.chain import default_chain
from skeleton.spine.digest import chain_digest
from skeleton.spine.law import VERTEBRA_N
from skeleton.spine.motion import (
    library,
    make_look_left_right,
    make_side_bend,
    make_sit_to_stand,
    motion_jerk_proxy,
    sample_timeline,
    validate_library_rom,
)
from skeleton.spine.posture import (
    BUILDERS,
    CATALOG,
    assert_postures_rom_safe,
    blend_postures,
    build_posture,
    list_postures,
    posture_energy_table,
)


class TestPostureBuilders(unittest.TestCase):
    def test_catalog_matches_builders(self) -> None:
        names = list_postures()
        self.assertEqual(set(names), set(BUILDERS))
        self.assertEqual(len(CATALOG), len(BUILDERS))
        self.assertGreaterEqual(len(names), 8)

    def test_each_builder_rom_safe(self) -> None:
        bad = assert_postures_rom_safe()
        self.assertEqual(bad, [])
        base = default_chain()
        for name in list_postures():
            p = build_posture(name, base)
            self.assertEqual(len(p.vertebrae), VERTEBRA_N)
            self.assertTrue(all_rom_ok(p.segments), name)
            self.assertEqual(p.name, name)

    def test_neutral_matches_default_topology(self) -> None:
        n = build_posture("neutral")
        d = default_chain()
        self.assertEqual(n.labels(), d.labels())

    def test_flexion_changes_digest(self) -> None:
        base = default_chain()
        f30 = build_posture("flexion_30", base)
        f60 = build_posture("flexion_60", base)
        self.assertNotEqual(chain_digest(base), chain_digest(f30))
        self.assertNotEqual(chain_digest(f30), chain_digest(f60))

    def test_blend_endpoints(self) -> None:
        a = build_posture("neutral")
        b = build_posture("flexion_30")
        near_a = blend_postures(a, b, 0.0)
        near_b = blend_postures(a, b, 1.0)
        mid = blend_postures(a, b, 0.5)
        self.assertTrue(all_rom_ok(near_a.segments))
        self.assertTrue(all_rom_ok(near_b.segments))
        self.assertTrue(all_rom_ok(mid.segments))
        # mid energy between endpoints for stiffness-like cost
        table = posture_energy_table()
        self.assertIn("neutral", table)
        self.assertIn("flexion_30", table)

    def test_unknown_posture_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_posture("not_a_real_posture")

    def test_lateral_symmetry_names(self) -> None:
        names = set(list_postures())
        self.assertIn("lateral_right_15", names)
        self.assertIn("lateral_left_15", names)
        self.assertIn("axial_cw_10", names)
        self.assertIn("axial_ccw_10", names)


class TestMotionLibrary(unittest.TestCase):
    def test_library_nonempty(self) -> None:
        lib = library()
        self.assertGreaterEqual(len(lib), 3)

    def test_clips_sample(self) -> None:
        for factory in (make_look_left_right, make_side_bend, make_sit_to_stand):
            clip = factory()
            samples = sample_timeline(clip, fps=5.0)
            self.assertGreater(len(samples), 0)
            for t, chain in samples:
                self.assertGreaterEqual(t, 0.0)
                self.assertEqual(len(chain.vertebrae), VERTEBRA_N)
                self.assertTrue(all_rom_ok(chain.segments))

    def test_validate_library_rom(self) -> None:
        result = validate_library_rom()
        self.assertTrue(all(result.values()), result)

    def test_jerk_proxy_nonnegative(self) -> None:
        clip = make_sit_to_stand()
        samples = [c for _, c in sample_timeline(clip, fps=4.0)]
        jerk = motion_jerk_proxy(samples)
        self.assertGreaterEqual(jerk, 0.0)


if __name__ == "__main__":
    unittest.main()
