"""Executable regression checks for the October 2026 frontier game milestones."""
from __future__ import annotations

import unittest

from skeleton.jeeves.game_frontier_dynamics import (
    AnticipatedPosition, Cloud, FrontierDynamicsError, FrameSample, InputObservation,
    PresentationClock, WindField, WindLayer, WindVector, WorldAxis,
    advect_clouds, anticipate_user_motion, generate_world_cell,
)
from skeleton.jeeves.game_frontier_production import (
    AnimationClip, AnimationKeyframe, Bone, BonePose, CharacterSkeleton,
    FrontierProductionError, Percept, Vec3, plan_cinematic, pose_skinned_mesh,
    reason_about_world, sample_animation, skeleton_to_polygon,
)


HASH = "a" * 64


def rig() -> CharacterSkeleton:
    return CharacterSkeleton((
        Bone("root", -1, Vec3(0, 0, 0), Vec3(0, 0, 2), .3),
        Bone("arm", 0, Vec3(0, 0, 1.5), Vec3(1, 0, 1.5), .1),
    ))


class WeatherTests(unittest.TestCase):
    def test_wind_is_deterministic(self):
        wind = WindField((WindLayer(0, WindVector(4, 2), 1.0),
                          WindLayer(2000, WindVector(-2, 8), .2)), seed=9)
        self.assertEqual(wind.sample(25, 30, 1000, 7), wind.sample(25, 30, 1000, 7))
        self.assertNotEqual(wind.sample(25, 30, 0, 7), wind.sample(25, 30, 2000, 7))

    def test_interpolated_vertical_wind(self):
        wind = WindField((WindLayer(0, WindVector(0, 0)),
                          WindLayer(1000, WindVector(10, 20))))
        self.assertEqual(wind.sample(0, 0, 500, 1), WindVector(5, 10))

    def test_midpoint_advection_and_wrap(self):
        wind = WindField((WindLayer(0, WindVector(3, -2)),))
        cloud = Cloud("c1", 99, 1, 100, .9)
        result = advect_clouds([cloud], wind, time_s=0, elapsed_s=2,
                               wrap_width_m=100, wrap_height_m=100)
        self.assertAlmostEqual(result[0].x_m, 5)
        self.assertAlmostEqual(result[0].y_m, 97)

    def test_shear_stretches_cloud(self):
        wind = WindField((WindLayer(0, WindVector(0, 0)),
                          WindLayer(200, WindVector(10, 0))))
        result = advect_clouds((Cloud("shear", 0, 0, 0, .5),),
                               wind, time_s=0, elapsed_s=10)
        self.assertGreater(result[0].stretch, 1)

    def test_bad_wind_rejected(self):
        with self.assertRaises(FrontierDynamicsError):
            WindField((WindLayer(0, WindVector(0, 0)),
                       WindLayer(0, WindVector(1, 1))))
        with self.assertRaises(FrontierDynamicsError):
            WindVector(float("nan"), 0)


class FramerateTests(unittest.TestCase):
    def test_all_30_50_120_modes(self):
        for fps in (30, 50, 120):
            clock = PresentationClock(fps)
            self.assertEqual(clock.deadline(fps), 1_000_000_000)
            frames = [clock.next_frame() for _ in range(fps + 1)]
            self.assertEqual(frames[-1].deadline_ns, 1_000_000_000)
            self.assertEqual(frames[5].fps, fps)

    def test_exact_due_and_drop_old_presentation_only(self):
        clock = PresentationClock(120)
        frames = clock.due(1_000_000_000, max_frames=3)
        self.assertEqual([f.frame_index for f in frames], [118, 119, 120])
        self.assertEqual(clock.index, 121)
        self.assertEqual(clock.due(1_000_000_000), ())

    def test_invalid_modes_rejected(self):
        for fps in (24, 60, 119, True):
            with self.assertRaises(FrontierDynamicsError):
                PresentationClock(fps)


class WorldAxesTests(unittest.TestCase):
    def setUp(self):
        self.axes = WorldAxis(8, .5, .8, .7, .5, .9, .4)

    def test_axis_repeatable(self):
        self.assertEqual(generate_world_cell(self.axes, 12, 5),
                         generate_world_cell(self.axes, 12, 5))

    def test_axis_affects_biomes_and_sky(self):
        a = generate_world_cell(self.axes, 12, 5)
        b = generate_world_cell(WorldAxis(8, .5, 0, 0, 0, 0, .4), 12, 5)
        self.assertNotEqual((a.humidity, a.temperature), (b.humidity, b.temperature))
        self.assertIn(a.biome, ("snow", "desert", "marsh", "mountain", "woodland", "grassland"))

    def test_negative_world_coordinates(self):
        self.assertEqual(generate_world_cell(self.axes, -20, -100).x, -20)


class PredictionTests(unittest.TestCase):
    def test_lookahead_is_bounded_and_proposal_only(self):
        sample = InputObservation(0, 0, 0, 10, -4, HASH)
        outcome = anticipate_user_motion(sample, horizon_ms=200)
        self.assertAlmostEqual(outcome.x, 2)
        self.assertAlmostEqual(outcome.y, -.8)
        self.assertEqual(outcome.authority, "speculative_never_auto_execute")
        self.assertGreaterEqual(outcome.confidence_upper_bound, 0)

    def test_prediction_refuses_long_horizon(self):
        sample = InputObservation(0, 0, 0, 0, 0, HASH)
        with self.assertRaises(FrontierDynamicsError):
            anticipate_user_motion(sample, horizon_ms=800)


class GeometryTests(unittest.TestCase):
    def test_era_lod_and_faces(self):
        skeleton = rig()
        old = skeleton_to_polygon(skeleton, "early_3d")
        modern = skeleton_to_polygon(skeleton, "modern")
        self.assertLess(old.triangle_count, modern.triangle_count)
        self.assertEqual(old.triangle_count, len(old.triangles))
        self.assertEqual(len(modern.colliders), len(skeleton.bones))
        self.assertEqual(modern.digest, skeleton_to_polygon(skeleton, "modern").digest)
        self.assertEqual(len(modern.vertices), len(modern.bone_influences))

    def test_restricted_triangle_budget(self):
        mesh = skeleton_to_polygon(rig(), "modern", max_triangles=24)
        self.assertEqual(mesh.triangle_count, 24)
        with self.assertRaises(FrontierProductionError):
            skeleton_to_polygon(rig(), "early_3d", max_triangles=12)

    def test_invalid_bone_parent_rejected(self):
        with self.assertRaises(FrontierProductionError):
            CharacterSkeleton((Bone("bad", 1, Vec3(0, 0, 0), Vec3(1, 0, 0), .1),))

    def test_clip_translation_updates_actual_vertices(self):
        skeleton = rig()
        mesh = skeleton_to_polygon(skeleton, "fixed_3d")
        zero = BonePose(Vec3(0, 0, 0))
        move = BonePose(Vec3(2, 0, 0))
        clip = AnimationClip("walk", (
            AnimationKeyframe(0, (zero, zero)),
            AnimationKeyframe(1000, (move, zero)),
        ), loop=False)
        at_zero = pose_skinned_mesh(skeleton, mesh, clip, 0)
        at_half = pose_skinned_mesh(skeleton, mesh, clip, 500)
        self.assertAlmostEqual(at_half[0].x - at_zero[0].x, 1)
        self.assertEqual(len(at_half), len(mesh.vertices))

    def test_animation_yaw_rotation_changes_position(self):
        skeleton = rig()
        mesh = skeleton_to_polygon(skeleton, "fixed_3d")
        zero = BonePose(Vec3(0, 0, 0))
        turn = BonePose(Vec3(0, 0, 0), math_pi_half())
        clip = AnimationClip("turn", (
            AnimationKeyframe(0, (zero, zero)),
            AnimationKeyframe(1000, (zero, turn)),
        ), loop=False)
        neutral = pose_skinned_mesh(skeleton, mesh, clip, 0)
        rotated = pose_skinned_mesh(skeleton, mesh, clip, 1000)
        self.assertNotEqual(neutral[len(neutral)//2], rotated[len(rotated)//2])


def math_pi_half() -> float:
    from math import pi
    return pi / 2


class CognitionTests(unittest.TestCase):
    def test_cinematic_evidence_grounding(self):
        events = [
            Percept("npc", "character", True, 2, .8, HASH),
            Percept("tower", "location", True, 50, .5, "b" * 64),
        ]
        c = plan_cinematic(events)
        self.assertEqual(c.shot, "closeup")
        self.assertEqual(c.focus_object_id, "npc")
        self.assertEqual(c.evidence_digests, (HASH,))
        self.assertEqual(c.authority, "proposal_only")
        self.assertEqual(plan_cinematic(events, player_in_danger=True).shot, "tracking_action")
        self.assertEqual(plan_cinematic(events, world_establishing=True).shot, "establishing_wide")

    def test_goal_proposals_cannot_execute(self):
        target = Percept("switch", "control", True, 2, .9, HASH)
        result = reason_about_world([target], goal_kind="control",
                                    available_actions=("inspect", "interact"))
        self.assertEqual((result.action, result.target), ("interact", "switch"))
        self.assertEqual(result.authority, "proposed_not_executed")

    def test_unobserved_goal_must_inspect(self):
        result = reason_about_world([], goal_kind="key",
                                    available_actions=("inspect", "approach"))
        self.assertEqual(result.action, "inspect")
        self.assertEqual(result.evidence_digests, ())
        with self.assertRaises(FrontierProductionError):
            reason_about_world([], goal_kind="key", available_actions=("approach",))


if __name__ == "__main__":
    unittest.main()
