"""GB-20 disc/facet/ligament/muscle/coupling/region ops."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.coupling import (
    DEFAULT_RULES,
    apply_coupling_to_pose,
    coordination_score,
    coupling_violations,
    enforce_coupling,
    neighbor_smoothness,
    rule_for_region,
)
from skeleton.spine.disc_mechanics import (
    axial_strain,
    bulging_mm,
    combined_risk,
    creep_height,
    disc_state,
    diurnal_cycle,
    fatigue_damage,
    height_under_load,
    hydrate_modulate,
    hydrostatic_pressure,
    poisson_radial_strain,
    rank_discs_by_risk,
    recovery_height,
    shear_from_pose,
)
from skeleton.spine.facet import (
    contact_force_n,
    facet_for,
    facet_map,
    facet_ok,
    guides_rotation,
    total_facet_load,
)
from skeleton.spine.ligament import (
    DEFAULT_LIGAMENTS,
    chain_ligament_energy,
    length_under_pose,
    ligament_energy,
    ligament_forces,
    restraining_moment,
)
from skeleton.spine.muscles import (
    MUSCLE_SET,
    co_contraction_index,
    metabolic_proxy,
    recruit_for_chain,
    recruit_for_pose,
    support_moment,
)
from skeleton.spine.posture import build_posture
from skeleton.spine.region_ops import (
    all_region_summaries,
    map_region_rx,
    region_energy,
    region_summary,
    scale_region_poses,
    segments_in_region,
    transform_region,
)
from skeleton.spine.taxonomy import Region
from skeleton.spine.vertebra import Pose6


class TestDiscMechanics(unittest.TestCase):

    def test_disc_slot_00(self) -> None:
        chain = default_chain()
        seg = chain.segments[0]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_01(self) -> None:
        chain = default_chain()
        seg = chain.segments[1]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_02(self) -> None:
        chain = default_chain()
        seg = chain.segments[2]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_03(self) -> None:
        chain = default_chain()
        seg = chain.segments[3]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_04(self) -> None:
        chain = default_chain()
        seg = chain.segments[4]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_05(self) -> None:
        chain = default_chain()
        seg = chain.segments[5]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_06(self) -> None:
        chain = default_chain()
        seg = chain.segments[6]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_07(self) -> None:
        chain = default_chain()
        seg = chain.segments[7]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_08(self) -> None:
        chain = default_chain()
        seg = chain.segments[8]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_09(self) -> None:
        chain = default_chain()
        seg = chain.segments[9]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_10(self) -> None:
        chain = default_chain()
        seg = chain.segments[10]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_11(self) -> None:
        chain = default_chain()
        seg = chain.segments[11]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_12(self) -> None:
        chain = default_chain()
        seg = chain.segments[12]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_13(self) -> None:
        chain = default_chain()
        seg = chain.segments[13]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_14(self) -> None:
        chain = default_chain()
        seg = chain.segments[14]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_15(self) -> None:
        chain = default_chain()
        seg = chain.segments[15]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_16(self) -> None:
        chain = default_chain()
        seg = chain.segments[16]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_17(self) -> None:
        chain = default_chain()
        seg = chain.segments[17]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_18(self) -> None:
        chain = default_chain()
        seg = chain.segments[18]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_19(self) -> None:
        chain = default_chain()
        seg = chain.segments[19]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_20(self) -> None:
        chain = default_chain()
        seg = chain.segments[20]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_21(self) -> None:
        chain = default_chain()
        seg = chain.segments[21]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_22(self) -> None:
        chain = default_chain()
        seg = chain.segments[22]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_disc_slot_23(self) -> None:
        chain = default_chain()
        seg = chain.segments[23]
        if seg.locked:
            self.assertTrue(True)
            return
        st = disc_state(seg, 100.0)
        self.assertIsNotNone(st)
        self.assertGreaterEqual(hydrostatic_pressure(seg.disc, 100.0), 0.0)
        self.assertIsInstance(axial_strain(seg.disc, 100.0), float)
        self.assertIsInstance(bulging_mm(seg.disc, 100.0), float)
        strain = axial_strain(seg.disc, 100.0)
        self.assertIsInstance(poisson_radial_strain(seg.disc, strain), float)
        self.assertIsInstance(shear_from_pose(seg, seg.relative), float)
        self.assertGreater(height_under_load(seg.disc, 50.0), 0.0)
        self.assertGreaterEqual(combined_risk(seg, 100.0, seg.relative), 0.0)
        crept = creep_height(seg.disc, 100.0, hours=2.0)
        self.assertGreater(crept, 0.0)
        self.assertGreaterEqual(recovery_height(crept, seg.disc, 1.0), 0.0)
        self.assertGreaterEqual(fatigue_damage(100, 1.5), 0.0)
        hydrated = hydrate_modulate(seg.disc, 1.1)
        self.assertIsNotNone(hydrated)

    def test_rank_and_diurnal(self) -> None:
        chain = default_chain()
        loads = [100.0] * len(chain.segments)
        ranked = rank_discs_by_risk(chain.segments, loads)
        self.assertEqual(len(ranked), len(chain.segments))
        cycle = diurnal_cycle(chain.segments[0], 120.0)
        self.assertEqual(len(cycle), 2)


class TestFacetLigamentMuscle(unittest.TestCase):
    def test_facet_map(self) -> None:
        chain = default_chain()
        fmap = facet_map(chain.segments)
        self.assertEqual(len(fmap), len(chain.segments))
        for s in chain.segments:
            fp = facet_for(s)
            self.assertIsNotNone(fp)
            self.assertIsInstance(facet_ok(s), bool)
            self.assertIsInstance(guides_rotation(fp, s.relative), float)
            self.assertGreaterEqual(contact_force_n(fp, 10.0), 0.0)
        self.assertGreaterEqual(total_facet_load(chain.segments, 400.0), 0.0)

    def test_ligaments(self) -> None:
        self.assertTrue(DEFAULT_LIGAMENTS)
        chain = default_chain()
        flexed = build_posture("flexion_30", chain)
        self.assertGreaterEqual(chain_ligament_energy(flexed.segments), 0.0)
        seg = next(s for s in flexed.segments if not s.locked)
        for lig in DEFAULT_LIGAMENTS[:3]:
            self.assertGreater(length_under_pose(lig, seg.relative, seg.disc.height_mm), 0.0)
        self.assertGreaterEqual(ligament_energy(seg), 0.0)
        forces = ligament_forces(seg)
        self.assertTrue(forces)
        self.assertIsInstance(restraining_moment(seg), float)

    def test_muscles(self) -> None:
        self.assertTrue(MUSCLE_SET)
        chain = build_posture("sitting")
        rec = recruit_for_chain(chain)
        self.assertTrue(rec)
        pose = chain.segments[0].relative
        self.assertTrue(recruit_for_pose(pose))
        self.assertGreaterEqual(co_contraction_index(rec), 0.0)
        self.assertGreaterEqual(metabolic_proxy(rec), 0.0)
        self.assertIsInstance(support_moment(rec), dict)


class TestCouplingAndRegions(unittest.TestCase):
    def test_coupling_rules(self) -> None:
        self.assertTrue(DEFAULT_RULES)
        for region in (Region.CERVICAL, Region.THORACIC, Region.LUMBAR):
            rule = rule_for_region(region)
            self.assertIsNotNone(rule)
        chain = build_posture("lateral_right_15")
        score = coordination_score(chain)
        self.assertGreaterEqual(score, 0.0)
        viol = coupling_violations(chain)
        self.assertIsInstance(viol, list)
        enforced = enforce_coupling(chain)
        self.assertEqual(len(enforced.vertebrae), len(chain.vertebrae))
        smooth = neighbor_smoothness(chain)
        self.assertIsInstance(smooth, float)
        pose = apply_coupling_to_pose(Region.LUMBAR, Pose6(rx=2.0, ry=1.0), 0.5, "type1")
        self.assertEqual(len(pose.as_tuple()), 6)

    def test_region_ops(self) -> None:
        chain = default_chain()
        for region in Region:
            segs = segments_in_region(chain, region)
            self.assertIsInstance(segs, list)
            summary = region_summary(chain, region)
            self.assertIsInstance(summary, dict)
            self.assertGreaterEqual(region_energy(chain, region), 0.0)
        summaries = all_region_summaries(chain)
        self.assertEqual(len(summaries), len(Region))
        mapped = map_region_rx(chain, Region.LUMBAR, 1.0)
        self.assertEqual(len(mapped.vertebrae), len(chain.vertebrae))
        scaled = scale_region_poses(chain, Region.CERVICAL, 0.5)
        self.assertEqual(len(scaled.segments), len(chain.segments))
        transformed = transform_region(
            chain, Region.THORACIC, lambda p: Pose6(rx=p.rx * 0.0)
        )
        self.assertEqual(len(transformed.vertebrae), len(chain.vertebrae))


if __name__ == "__main__":
    unittest.main()
