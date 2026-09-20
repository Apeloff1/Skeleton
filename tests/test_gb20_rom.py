"""GB-20 ROM clamp / articulation / clinical ROM tests."""

from __future__ import annotations

import unittest

from skeleton.spine.articulation import (
    aggregate_rom_volume,
    all_rom_ok,
    assert_dof_contract,
    check_rom,
    clamp_to_rom,
    dof_active,
    rom_for_segment,
    rom_map,
    rom_violations,
    soft_penalty,
    total_soft_penalty,
)
from skeleton.spine.chain import default_chain, rebind_segments
from skeleton.spine.range_of_motion import (
    CLINICAL,
    cumulative_extension_capacity,
    cumulative_flexion_capacity,
    distribute_flexion,
    fryette_type1,
    fryette_type2,
    mean_utilization,
    region_total_rom,
    rom_utilization,
)
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.taxonomy import Region
from skeleton.spine.vertebra import Pose6


class TestRomClamp(unittest.TestCase):
    def test_default_all_ok(self) -> None:
        chain = default_chain()
        self.assertTrue(all_rom_ok(chain.segments))
        self.assertEqual(rom_violations(chain.segments), [])

    def test_clamp_extreme(self) -> None:
        chain = default_chain()
        seg = next(s for s in chain.segments if not s.locked)
        wild = Pose6(rx=1e6, ry=-1e6, rz=1e6, tx=1e6, ty=-1e6, tz=1e6)
        clamped = clamp_to_rom(seg, wild)
        self.assertTrue(rom_for_segment(seg).contains(clamped))
        self.assertTrue(check_rom(seg, clamped))

    def test_violation_detected(self) -> None:
        chain = default_chain()
        seg = next(s for s in chain.segments if not s.locked)
        bad = rebind_segments(
            chain, apply_relative_map(chain.segments, {seg.label: Pose6(rx=999.0)})
        )
        self.assertFalse(all_rom_ok(bad.segments))
        self.assertIn(seg.label, rom_violations(bad.segments))

    def test_dof_contract(self) -> None:
        chain = default_chain()
        assert_dof_contract(chain.segments)
        for s in chain.segments:
            if not s.locked:
                self.assertGreaterEqual(dof_active(s), 3)

    def test_rom_map_covers_segments(self) -> None:
        chain = default_chain()
        rm = rom_map(chain.segments)
        self.assertEqual(len(rm), len(chain.segments))

    def test_aggregate_volume_positive(self) -> None:
        chain = default_chain()
        self.assertGreater(aggregate_rom_volume(chain.segments), 0.0)

    def test_soft_penalty_zero_inside(self) -> None:
        chain = default_chain()
        self.assertEqual(total_soft_penalty(chain.segments), 0.0)
        seg = next(s for s in chain.segments if not s.locked)
        self.assertEqual(soft_penalty(seg, seg.relative), 0.0)
        self.assertGreater(soft_penalty(seg, Pose6(rx=999.0)), 0.0)

    def test_distribute_flexion_stays_in_rom(self) -> None:
        chain = default_chain()
        rel = distribute_flexion(chain.segments, 30.0)
        posed = rebind_segments(chain, apply_relative_map(chain.segments, rel))
        self.assertTrue(all_rom_ok(posed.segments))
        total_rx = sum(posed.segments[i].relative.rx for i in range(len(posed.segments)))
        self.assertAlmostEqual(total_rx, 30.0, places=3)

    def test_clinical_catalog(self) -> None:
        self.assertTrue(CLINICAL)
        for region in (Region.CERVICAL, Region.THORACIC, Region.LUMBAR):
            total = region_total_rom(region)
            self.assertIsInstance(total, dict)
            self.assertTrue(any(v > 0 for v in total.values()))

    def test_cumulative_capacities(self) -> None:
        chain = default_chain()
        self.assertGreater(cumulative_flexion_capacity(chain.segments), 0.0)
        self.assertGreater(cumulative_extension_capacity(chain.segments), 0.0)

    def test_utilization_neutral_zero(self) -> None:
        chain = default_chain()
        self.assertAlmostEqual(mean_utilization(chain.segments), 0.0, places=6)
        for s in chain.segments:
            self.assertAlmostEqual(rom_utilization(s), 0.0, places=6)

    def test_fryette_helpers(self) -> None:
        self.assertIsInstance(fryette_type1(5.0, -5.0), bool)
        self.assertIsInstance(fryette_type2(5.0, 5.0, True), bool)
        self.assertTrue(fryette_type1(5.0, -5.0) or not fryette_type1(5.0, -5.0))


class TestRomBoundsProperties(unittest.TestCase):
    def test_bounds_lo_hi_ordered(self) -> None:
        chain = default_chain()
        for s in chain.segments:
            b = rom_for_segment(s)
            lo, hi = b.lo.as_tuple(), b.hi.as_tuple()
            for i in range(6):
                self.assertLessEqual(lo[i], hi[i])

    def test_locked_segments_zero_or_tight(self) -> None:
        chain = default_chain()
        locked = [s for s in chain.segments if s.locked]
        self.assertTrue(locked)
        for s in locked:
            self.assertTrue(check_rom(s))


if __name__ == "__main__":
    unittest.main()
