"""Qualification and end-to-end scene candidate regression checks.

No GPU, external models, provider calls, or ROM downloads are performed.
"""
import unittest

from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.jeeves.game_frontier_dynamics import (
    Cloud, InputObservation, WindField, WindLayer, WindVector, WorldAxis,
)
from skeleton.jeeves.game_frontier_production import (
    AnimationClip, AnimationKeyframe, Bone, BonePose,
    CharacterSkeleton, Percept, Vec3,
)
from skeleton.jeeves.game_frontier_qualification import (
    FrameInferenceEvidence, FrontierQualificationError, RuntimeAdmittance,
    SimReady3DArtifact, WorldFrameRequest, WorldModelCheckpoint,
    qualify_frame_performance,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64


class WorldFrameQualificationTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint = WorldModelCheckpoint(
            "local-authorized-model", A, "test-license", "test-only",
            "generic-registered-world-model", ("action_conditioned_frame",),
            True, True,
        )

    def request(self, n):
        return WorldFrameRequest(A, self.checkpoint, B, C, n, 50, n * 20_000_000)

    def response(self, n):
        return FrameInferenceEvidence(
            n, A, B, C, A, B,
            n * 20_000_000, n * 20_000_000 + 2_000_000,
            n * 20_000_000 + 3_000_000, C,
        )

    def test_measured_rate_separate_from_requested(self):
        # Two emitted frames in 100ms == 20Hz, not the requested 50Hz.
        value = qualify_frame_performance(
            (self.request(0), self.request(1)),
            (self.response(0), self.response(1)),
            observation_start_ns=0, observation_end_ns=100_000_000,
            approved_licenses=("test-license",),
        )
        self.assertEqual(value.requested_fps, 50)
        self.assertAlmostEqual(value.measured_generation_fps, 20)
        self.assertAlmostEqual(value.p95_inference_latency_ms, 2)
        self.assertFalse(value.meets_requested_presentation_fps)
        self.assertEqual(value.authority, "reported_external_receipts_not_host_verified")

    def test_explicit_license_allowlist(self):
        with self.assertRaises(FrontierQualificationError):
            qualify_frame_performance(
                (self.request(0),), (self.response(0),),
                observation_start_ns=0, observation_end_ns=100_000_000,
                approved_licenses=("not-approved",),
            )

    def test_required_model_checkpoint_availability(self):
        absent = WorldModelCheckpoint("m", A, "license", "test", "baseline",
                                      ("action_conditioned_frame",), False, True)
        with self.assertRaises(FrontierQualificationError):
            absent.require_ready(capability="action_conditioned_frame",
                                 allowed_licenses=("license",))

    def test_wrong_model_or_action_fails(self):
        bad = FrameInferenceEvidence(0, A, B, A, A, B, 0, 2, 3, C)
        with self.assertRaises(FrontierQualificationError):
            qualify_frame_performance(
                (self.request(0),), (bad,), observation_start_ns=0,
                observation_end_ns=1_000_000_000,
                approved_licenses=("test-license",),
            )

    def test_duplicate_frames_fail(self):
        with self.assertRaises(FrontierQualificationError):
            qualify_frame_performance(
                (self.request(0), self.request(0)),
                (self.response(0), self.response(0)),
                observation_start_ns=0, observation_end_ns=100_000_000,
                approved_licenses=("test-license",),
            )


class SimArtifactTests(unittest.TestCase):
    def test_artifact_digest_and_lod_validation(self):
        item = SimReady3DArtifact(A, B, C, A, (B,), (240, 96, 24),
                                  8, 16, B, C)
        self.assertEqual(item.candidate_digest, item.candidate_digest)
        with self.assertRaises(FrontierQualificationError):
            SimReady3DArtifact(A, B, C, A, (B,), (24, 96), 8, 16, B, C)

    def test_candidate_does_not_auto_admit(self):
        r = RuntimeAdmittance(A, ("mesh", "anim"), B, False)
        self.assertFalse(r.qualified_by_contract(required_ids=("mesh",)))
        self.assertFalse(RuntimeAdmittance(A, ("mesh",), B, True)
                         .qualified_by_contract(required_ids=("mesh", "sim")))


class FrontierCompositionTests(unittest.TestCase):
    def test_scene_records_all_seven_features_as_candidate(self):
        skeleton = CharacterSkeleton((
            Bone("root", -1, Vec3(0, 0, 0), Vec3(0, 0, 1), .2),
        ))
        zero = BonePose(Vec3(0, 0, 0))
        move = BonePose(Vec3(.3, 0, 0))
        clip = AnimationClip("idle", (
            AnimationKeyframe(0, (zero,)),
            AnimationKeyframe(1000, (move,)),
        ))
        params = dict(
            world_axes=WorldAxis(123, .6, .4, .7, .8, .9, .3),
            cell_x=0, cell_y=-2,
            wind_field=WindField((WindLayer(0, WindVector(1, 0)),)),
            clouds=(Cloud("stratus", 20, 30, 0, .8),),
            time_s=100, delta_s=5,
            skeleton=skeleton, animation=clip, animation_time_ms=100,
            era="early_3d", fps=120,
            evidence=(Percept("npc", "character", True, 2, .8, A),),
            world_goal_kind="character",
            available_actions=("inspect", "interact", "approach"),
            speculative_input=InputObservation(0, 0, 0, 1, 2, B),
        )
        output = compile_frontier_scene(**params)
        self.assertEqual(output.manifest_digest, compile_frontier_scene(**params).manifest_digest)
        self.assertEqual(output.manifest["render"]["fps"], 120)
        self.assertGreater(output.manifest["render"]["triangle_count"], 0)
        self.assertNotEqual(output.moved_clouds[0].x_m, 20)
        self.assertEqual(output.manifest["cognition"]["suggested_action"], "interact")
        self.assertFalse(output.approved_for_runtime)
        self.assertFalse(output.manifest["governance"]["neural_model_checkpoint_loaded"])
        self.assertEqual(output.manifest["preemptive_input"]["authority"],
                         "speculative_never_auto_execute")


if __name__ == "__main__":
    unittest.main()
