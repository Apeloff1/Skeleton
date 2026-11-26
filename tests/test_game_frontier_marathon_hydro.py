"""Shoreline volume, atmosphere mixer, skin/fascia integration, instrument replay.

These tests fail closed when liquid is deleted, hostile numbers are accepted,
PCM stops being deterministic, pinned rig nodes drift, or a game-time
instrument journal cannot be replayed.
"""

from __future__ import annotations

import ast
import json
import math
import unittest
from pathlib import Path

from skeleton.frontier_body.atmosphere_audio import (
    BUS_NAMES,
    AudioMixError,
    AtmosphereAudioFrame,
    BlockerSegment,
    blocker_occlusion,
    parameter_stream,
    render_pcm_preview,
)
from skeleton.frontier_body.instrument_journal import (
    SIMULATED_LABEL,
    CalibrationEpoch,
    InstrumentJournalError,
    SimulatedReading,
    append_reading,
    dump_instrument_journal,
    load_instrument_journal,
    open_instrument_journal,
    replay_instrument_journal,
)
from skeleton.frontier_body.integration import (
    AnatomicalSkinIntegrator,
    ReferenceAnatomicalSkinIntegrator,
    SkinIntegrationError,
    SkinIntegrationRequest,
)
from skeleton.frontier_body.shoreline import (
    VOLUME_CONSERVATION_EPSILON_M3,
    CollisionBox,
    CoastalJournal,
    ShorelineError,
    commit_coastal_terrain,
    dump_coastal_journal,
    load_coastal_journal,
    step_coastal_liquid,
)
from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions,
    CelestialCycle,
    LiquidGrid,
    sample_atmosphere,
)
from skeleton.jeeves.game_frontier_motion import CharacterState, CollisionPlane
from skeleton.jeeves.game_frontier_production import (
    AnimationClip,
    AnimationKeyframe,
    Bone,
    BonePose,
    CharacterSkeleton,
    Vec3,
    pose_skinned_mesh,
    skeleton_to_polygon,
)


def _pool() -> LiquidGrid:
    return LiquidGrid(4, 1, 1.0, (0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 1.0))


def _frame(**overrides) -> AtmosphereAudioFrame:
    base = dict(
        game_time_s=1.0,
        air=AirConditions(altitude_m=830, temperature_c=15, rain_mm_h=40),
        source=Vec3(0, 0, 0),
        listener=Vec3(4, 0, 0),
        intensity=1.0,
        blockers=(),
        tide=CelestialCycle(time_hours=3),
        ui_gain=0.4,
    )
    base.update(overrides)
    return AtmosphereAudioFrame(**base)


def _rig():
    skeleton = CharacterSkeleton((
        Bone("torso", -1, Vec3(0, 0, 0), Vec3(0, 0, 1.4), 0.2),
    ))
    mesh = skeleton_to_polygon(skeleton, "early_3d")
    clip = AnimationClip("walk", (
        AnimationKeyframe(0, (BonePose(Vec3(0, 0, 0), 0.0),)),
        AnimationKeyframe(1000, (BonePose(Vec3(0.2, 0, 0), 0.5),)),
    ))
    return skeleton, mesh, clip


def _request(**overrides) -> SkinIntegrationRequest:
    skeleton, mesh, clip = _rig()
    base = dict(
        skeleton=skeleton,
        mesh=mesh,
        clip=clip,
        collision_impulse_n=Vec3(0, 0, 0),
        wetness=0.0,
        stride_m=0.0,
        stride_length_m=2.0,
        delta_s=0.05,
        game_time_s=4.0,
        pinned_vertices=(0,),
    )
    base.update(overrides)
    return SkinIntegrationRequest(**base)


def _epoch(epoch_id="epoch-a", **overrides) -> CalibrationEpoch:
    base = dict(
        epoch_id=epoch_id,
        gyro_bias_dps=(0.0, 0.0, 0.1),
        gyro_drift_dps=(0.0, 0.0, 0.0),
        compass_declination_deg=12.0,
        sextant_index_error_deg=0.0,
        barometer_reference_pa=101325.0,
    )
    base.update(overrides)
    return CalibrationEpoch(**base)


class ShorelineTests(unittest.TestCase):
    def test_advance_retreat_and_obstacle_conserve_volume(self):
        source = _pool()
        original = source.volume_m3
        advanced = step_coastal_liquid(grid=source, shore_column=1.0, delta_s=0.2)
        self.assertEqual(advanced.grid.water_depth_m[0], 0.0)
        self.assertGreater(advanced.grid.water_depth_m[1], 1.0)
        self.assertLessEqual(advanced.volume_error_m3, VOLUME_CONSERVATION_EPSILON_M3)
        self.assertAlmostEqual(advanced.final_volume_m3, original, delta=VOLUME_CONSERVATION_EPSILON_M3)

        retreated = step_coastal_liquid(grid=advanced.grid, shore_column=0.0, delta_s=0.2)
        self.assertGreater(retreated.grid.water_depth_m[0], 0.0)
        self.assertAlmostEqual(retreated.final_volume_m3, original, delta=VOLUME_CONSERVATION_EPSILON_M3)

        box = CollisionBox(0.0, 0.0, -1.0, 1.0, 1.0, 5.0)
        blocked = step_coastal_liquid(
            grid=retreated.grid, shore_column=0.0, delta_s=0.0, obstacles=(box,),
        )
        plain = step_coastal_liquid(grid=retreated.grid, shore_column=0.0, delta_s=0.0)
        self.assertEqual(blocked.grid.water_depth_m[0], 0.0)
        self.assertLess(blocked.grid.water_depth_m[0], plain.grid.water_depth_m[0])
        self.assertAlmostEqual(blocked.final_volume_m3, original, delta=VOLUME_CONSERVATION_EPSILON_M3)
        self.assertAlmostEqual(sum(blocked.grid.water_depth_m), original, delta=VOLUME_CONSERVATION_EPSILON_M3)

    def test_direct_obstacle_insertion_relocates_water(self):
        source = _pool()
        box = CollisionBox(0.0, 0.0, -1.0, 1.0, 1.0, 5.0)
        blocked = step_coastal_liquid(grid=source, shore_column=0.0, delta_s=0.0, obstacles=(box,))
        self.assertEqual(blocked.grid.water_depth_m[0], 0.0)
        self.assertGreater(blocked.grid.water_depth_m[1], source.water_depth_m[1])
        self.assertAlmostEqual(blocked.final_volume_m3, source.volume_m3, delta=VOLUME_CONSERVATION_EPSILON_M3)

    def test_hostile_cell_size_and_nan_height_reject_the_step(self):
        beds = (0.0, 0.0, 0.0, 0.0)
        depths = (1.0, 1.0, 1.0, 1.0)
        with self.assertRaises(ShorelineError):
            step_coastal_liquid(
                width=4, height=1, cell_size_m=-1.0, bed_elevation_m=beds,
                water_depth_m=depths, shore_column=0.0, delta_s=0.1,
            )
        with self.assertRaises(ShorelineError):
            step_coastal_liquid(
                width=4, height=1, cell_size_m=1.0,
                bed_elevation_m=(math.nan, 0.0, 0.0, 0.0),
                water_depth_m=depths, shore_column=0.0, delta_s=0.1,
            )
        with self.assertRaises(ShorelineError):
            CollisionBox(0.0, 0.0, math.nan, 1.0, 1.0, 1.0)

    def test_coastal_bed_survives_journal_save_and_load(self):
        beds = (0.0, 1.5, -0.25, 2.0)
        stepped = step_coastal_liquid(
            width=4, height=1, cell_size_m=1.0, bed_elevation_m=beds,
            water_depth_m=(0.4, 0.2, 0.3, 0.1), shore_column=0.0, delta_s=0.2,
        )
        self.assertEqual(stepped.terrain.bed_elevation_m, beds)
        journal = commit_coastal_terrain(CoastalJournal(), stepped.terrain, game_time_s=12.0)
        loaded = load_coastal_journal(dump_coastal_journal(journal))
        self.assertEqual(loaded.entries[0].terrain.bed_elevation_m, beds)
        self.assertEqual(loaded.entries[0].terrain.cell_size_m, 1.0)
        tampered = json.loads(dump_coastal_journal(journal))
        tampered["entries"][0]["bed_elevation_m"][1] = 9.0
        with self.assertRaises(ShorelineError):
            load_coastal_journal(json.dumps(tampered))


class AtmosphereAudioTests(unittest.TestCase):
    def test_occlusion_is_blocker_geometry(self):
        source = Vec3(0, 0, 0)
        listener = Vec3(4, 0, 0)
        crossing = BlockerSegment(Vec3(2, -1, 0), Vec3(2, 1, 0), transmission=0.0)
        missing = BlockerSegment(Vec3(2, 3, 0), Vec3(3, 4, 0), transmission=0.0)
        partial = BlockerSegment(Vec3(2, -1, 0), Vec3(2, 1, 0), transmission=0.5)
        self.assertEqual(blocker_occlusion(source, listener, ()), 0.0)
        self.assertEqual(blocker_occlusion(source, listener, (missing,)), 0.0)
        self.assertEqual(blocker_occlusion(source, listener, (crossing,)), 1.0)
        self.assertAlmostEqual(blocker_occlusion(source, listener, (partial, partial)), 0.75)

    def test_parameters_come_from_the_atmosphere_model(self):
        frame = _frame()
        blocked = _frame(blockers=(BlockerSegment(Vec3(2, -1, 0), Vec3(2, 1, 0), transmission=0.0),))
        clear_rows = parameter_stream((frame,))
        blocked_rows = parameter_stream((blocked,))
        self.assertEqual([row.bus for row in clear_rows], list(BUS_NAMES))
        atmosphere = sample_atmosphere(frame.air)
        distance = 4.0
        for row in clear_rows:
            if row.bus == "ui":
                self.assertEqual(row.delay_s, 0.0)
                self.assertEqual(row.occlusion, 0.0)
            else:
                self.assertAlmostEqual(row.delay_s, distance / atmosphere.sound_speed_m_s, places=9)
        clear_occlusion = {row.bus: row for row in clear_rows}
        blocked_occlusion = {row.bus: row for row in blocked_rows}
        self.assertEqual(blocked_occlusion["occlusion"].occlusion, 1.0)
        self.assertAlmostEqual(
            blocked_occlusion["occlusion"].gain,
            clear_occlusion["occlusion"].gain * 0.35,
            places=9,
        )
        self.assertLess(blocked_occlusion["occlusion"].low_pass_hz, clear_occlusion["occlusion"].low_pass_hz)
        dry = parameter_stream((_frame(air=AirConditions(altitude_m=830, rain_mm_h=0)),))
        wet = parameter_stream((_frame(air=AirConditions(altitude_m=830, rain_mm_h=90)),))
        self.assertGreater(
            {row.bus: row for row in wet}["weather"].gain,
            {row.bus: row for row in dry}["weather"].gain,
        )
        self.assertLess(
            {row.bus: row for row in wet}["weather"].low_pass_hz,
            {row.bus: row for row in dry}["weather"].low_pass_hz,
        )

    def test_pcm_preview_is_deterministic_and_occlusion_changes_it(self):
        frame = _frame()
        blocked = _frame(blockers=(BlockerSegment(Vec3(2, -1, 0), Vec3(2, 1, 0)),))
        first = render_pcm_preview((frame, _frame(game_time_s=2.0)))
        second = render_pcm_preview((_frame(game_time_s=2.0), frame))
        self.assertEqual(first, second)
        self.assertTrue(any(sample != 0 for sample in first))
        self.assertEqual(len(first), 128)
        self.assertNotEqual(first, render_pcm_preview((blocked, _frame(game_time_s=2.0, blockers=blocked.blockers))))
        with self.assertRaises(AudioMixError):
            AtmosphereAudioFrame(
                game_time_s=math.nan, air=AirConditions(), source=Vec3(0, 0, 0), listener=Vec3(1, 0, 0),
            )


class SkinIntegrationTests(unittest.TestCase):
    def test_protocol_and_no_frontier_runtime_import(self):
        integrator = ReferenceAnatomicalSkinIntegrator()
        self.assertIsInstance(integrator, AnatomicalSkinIntegrator)
        root = Path(__file__).resolve().parents[1] / "skeleton" / "frontier_body"
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                self.assertNotIn("frontier_runtime", names)

    def test_impulse_wetness_and_stride_move_skin_without_pin_drift(self):
        integrator = ReferenceAnatomicalSkinIntegrator()
        still = integrator.integrate_character_skin(_request())
        struck = integrator.integrate_character_skin(_request(collision_impulse_n=Vec3(30, 0, 0)))
        self.assertGreater(struck.skin.mean_anchor_displacement_m, still.skin.mean_anchor_displacement_m)
        wet = integrator.integrate_character_skin(_request(collision_impulse_n=Vec3(30, 0, 0), wetness=1.0))
        self.assertGreater(wet.wetness, struck.wetness)
        self.assertNotEqual(wet.skin.positions[1], struck.skin.positions[1])
        dry_cloth = integrator.integrate_character_skin(_request(collision_impulse_n=Vec3(0.15, 0, 0)))
        wet_cloth = integrator.integrate_character_skin(
            _request(collision_impulse_n=Vec3(0.15, 0, 0), wetness=1.0),
        )
        self.assertNotEqual(dry_cloth.cloth[1].position, wet_cloth.cloth[1].position)
        self.assertEqual(dry_cloth.fascia[0].position, dry_cloth.anchor_positions[0])
        rested = integrator.integrate_character_skin(_request(stride_m=0.0))
        striding = integrator.integrate_character_skin(_request(stride_m=1.0))
        self.assertNotEqual(rested.stride_time_ms, striding.stride_time_ms)
        skeleton, mesh, clip = _rig()
        anchors = pose_skinned_mesh(skeleton, mesh, clip, striding.stride_time_ms)
        self.assertEqual(striding.skin.positions[0], anchors[0])
        self.assertEqual(striding.fascia[0].position, anchors[0])
        self.assertNotEqual(striding.skin.positions[0], rested.skin.positions[0])
        self.assertLessEqual(striding.max_strain, 0.5 + 1e-6)
        again = integrator.integrate_character_skin(_request(collision_impulse_n=Vec3(30, 0, 0), wetness=1.0))
        self.assertEqual(wet, again)

    def test_large_impulse_keeps_strain_inside_the_tether(self):
        integrator = ReferenceAnatomicalSkinIntegrator()
        result = integrator.integrate_character_skin(_request(collision_impulse_n=Vec3(5000, 0, 0), delta_s=0.1))
        limit = 0.5 * 1.4
        for index, node in enumerate(result.cloth):
            delta = node.position - result.anchor_positions[index]
            distance = math.sqrt(delta.dot(delta))
            self.assertLessEqual(distance, limit + 1e-6)
            self.assertGreater(distance, 0.0)
        self.assertEqual(result.fascia[0].position, result.anchor_positions[0])
        self.assertLessEqual(result.max_strain, 0.5 + 1e-6)

    def test_locomotion_and_collision_feed_the_integrator(self):
        integrator = ReferenceAnatomicalSkinIntegrator()
        character = CharacterState(Vec3(0, 0, 1), Vec3(0, 0, 0), 0.3, 70)
        walking = integrator.integrate_character_skin(_request(
            locomotion=character,
            desired_velocity=Vec3(1.2, 0, 0),
        ))
        self.assertTrue(walking.locomotion_applied)
        self.assertEqual(walking.gait, "walk")
        self.assertGreater(walking.stride_m, 0.0)
        grounded = CharacterState(Vec3(0, 0, 0.2), Vec3(0, 0, 0), 0.3, 70)
        plane = CollisionPlane("ground", Vec3(0, 0, 0), Vec3(0, 0, 1), "stone")
        impacted = integrator.integrate_character_skin(_request(
            locomotion=grounded,
            surfaces=(plane,),
            desired_velocity=Vec3(0, 0, 0),
        ))
        free = integrator.integrate_character_skin(_request(
            locomotion=grounded,
            desired_velocity=Vec3(0, 0, 0),
        ))
        self.assertNotEqual(impacted.collision_impulse_n, free.collision_impulse_n)
        self.assertNotEqual(impacted.skin.positions[1], free.skin.positions[1])

    def test_hostile_skin_input_is_rejected(self):
        with self.assertRaises(SkinIntegrationError):
            _request(wetness=math.nan)
        with self.assertRaises(SkinIntegrationError):
            _request(stride_m=-1.0)


class InstrumentJournalTests(unittest.TestCase):
    def _journal(self, calibration=None):
        return open_instrument_journal(
            calibration=calibration or _epoch(),
            origin_game_time_s=0.0,
            latitude_deg=60.0,
            longitude_deg=10.0,
            altitude_m=830.0,
        )

    def test_game_time_replay_and_epoch_rejection(self):
        pressure = sample_atmosphere(AirConditions(altitude_m=830, temperature_c=15)).pressure_pa
        journal = append_reading(
            self._journal(),
            game_time_s=5.0,
            angular_rate_dps=(1.0, 0.0, 10.0),
            true_heading_deg=100.0,
            observed_pressure_pa=pressure,
            air_temperature_c=15.0,
        )
        first = journal.entries[0].reading
        self.assertEqual(first.label, SIMULATED_LABEL)
        self.assertTrue(first.simulated)
        self.assertIn("simulated", first.authority)
        self.assertIn("simulated", first.ephemeris)
        self.assertAlmostEqual(first.yaw_deg, 50.5, places=6)
        self.assertAlmostEqual(first.magnetic_heading_deg, 88.0, places=6)
        self.assertNotEqual(first.solar_direction_enu, first.lunar_direction_enu)
        later = append_reading(
            journal,
            game_time_s=6.0,
            angular_rate_dps=(0.0, 0.0, 0.0),
            true_heading_deg=100.0,
            observed_pressure_pa=pressure,
            air_temperature_c=15.0,
            calibration=_epoch(
                "epoch-b",
                compass_declination_deg=20.0,
                sextant_index_error_deg=0.2,
                barometer_reference_pa=100000.0,
            ),
        )
        second = later.entries[1].reading
        self.assertNotAlmostEqual(second.magnetic_heading_deg, first.magnetic_heading_deg, places=6)
        self.assertNotAlmostEqual(second.barometric_altitude_m, first.barometric_altitude_m, places=4)
        self.assertNotEqual(second.solar_direction_enu, first.solar_direction_enu)
        self.assertEqual(replay_instrument_journal(later), tuple(entry.reading for entry in later.entries))
        restored = load_instrument_journal(dump_instrument_journal(later))
        self.assertEqual(replay_instrument_journal(restored), replay_instrument_journal(later))
        with self.assertRaises(InstrumentJournalError):
            append_reading(
                journal,
                game_time_s=6.0,
                angular_rate_dps=(0.0, 0.0, 0.0),
                true_heading_deg=100.0,
                observed_pressure_pa=pressure,
                air_temperature_c=15.0,
                calibration=_epoch(compass_declination_deg=20.0),
            )
        with self.assertRaises(InstrumentJournalError):
            append_reading(
                later,
                game_time_s=6.0,
                angular_rate_dps=(0.0, 0.0, 0.0),
                true_heading_deg=100.0,
                observed_pressure_pa=pressure,
                air_temperature_c=15.0,
            )
        with self.assertRaises(InstrumentJournalError):
            SimulatedReading(
                0, "device-gps", False, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101325,
                (0, 0, 1), (0, 0, 1),
            )

    def test_index_error_and_identical_game_time_are_deterministic(self):
        pressure = 101000.0
        plain = append_reading(
            self._journal(_epoch(sextant_index_error_deg=0.0)),
            game_time_s=8.0,
            angular_rate_dps=(0.0, 0.0, 0.0),
            true_heading_deg=10.0,
            observed_pressure_pa=pressure,
            air_temperature_c=15.0,
        )
        indexed = append_reading(
            self._journal(_epoch(sextant_index_error_deg=0.4)),
            game_time_s=8.0,
            angular_rate_dps=(0.0, 0.0, 0.0),
            true_heading_deg=10.0,
            observed_pressure_pa=pressure,
            air_temperature_c=15.0,
        )
        self.assertAlmostEqual(
            indexed.entries[0].reading.sextant_apparent_altitude_deg
            - plain.entries[0].reading.sextant_apparent_altitude_deg,
            0.4,
            places=6,
        )
        self.assertAlmostEqual(
            indexed.entries[0].reading.sextant_corrected_altitude_deg,
            plain.entries[0].reading.sextant_corrected_altitude_deg,
            places=6,
        )
        twin = append_reading(
            self._journal(_epoch(sextant_index_error_deg=0.4)),
            game_time_s=8.0,
            angular_rate_dps=(0.0, 0.0, 0.0),
            true_heading_deg=10.0,
            observed_pressure_pa=pressure,
            air_temperature_c=15.0,
        )
        self.assertEqual(dump_instrument_journal(indexed), dump_instrument_journal(twin))

    def test_tamper_and_wall_clock_are_rejected(self):
        journal = append_reading(
            self._journal(),
            game_time_s=3.0,
            angular_rate_dps=(0.0, 0.0, 1.0),
            true_heading_deg=20.0,
            observed_pressure_pa=100000.0,
            air_temperature_c=15.0,
        )
        payload = json.loads(dump_instrument_journal(journal))
        payload["entries"][0]["reading"]["yaw_deg"] = 1.0
        with self.assertRaises(InstrumentJournalError):
            load_instrument_journal(json.dumps(payload))
        source = Path(open_instrument_journal.__code__.co_filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in imported:
                self.assertNotIn(name, {"time", "datetime", "os", "gps", "geolocation"})
        self.assertNotIn("time.time", source)
        self.assertNotIn("datetime.now", source)


if __name__ == "__main__":
    unittest.main()
