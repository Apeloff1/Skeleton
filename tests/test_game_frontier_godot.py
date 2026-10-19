"""Godot overlay import evidence: source files only, no engine execution."""
from dataclasses import replace
import json
import unittest

from skeleton.forge.game_frontier_godot import (
    FrontierGodotError, emit_frontier_godot_overlay,
)
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.jeeves.game_frontier_dynamics import (
    Cloud, WindField, WindLayer, WindVector, WorldAxis,
)
from skeleton.jeeves.game_frontier_production import (
    AnimationClip, AnimationKeyframe, Bone, BonePose,
    CharacterSkeleton, Percept, Vec3,
)


def source_scene():
    skeleton = CharacterSkeleton((
        Bone("torso", -1, Vec3(0, 0, 0), Vec3(0, 0, 2), .25),
    ))
    zero = BonePose(Vec3(0, 0, 0))
    clip = AnimationClip("idle", (
        AnimationKeyframe(0, (zero,)),
        AnimationKeyframe(1000, (BonePose(Vec3(.1, 0, 0)),)),
    ))
    return compile_frontier_scene(
        world_axes=WorldAxis(2, .7, .6, .6, .9, 1.0, .5),
        cell_x=-2, cell_y=4,
        wind_field=WindField((
            WindLayer(0, WindVector(5, 0), .8, 40),
            WindLayer(1000, WindVector(2, 3), .2, 100),
        ), seed=998, gust_period_s=3),
        clouds=(Cloud("shelf", 1, 2, 300, .8),),
        time_s=10, delta_s=2,
        skeleton=skeleton, animation=clip, animation_time_ms=0,
        era="early_3d", fps=120,
        evidence=(Percept("actor", "character", True, 1, 1,
                          "f" * 64),),
        world_goal_kind="character",
        available_actions=("inspect", "interact"),
    )


class ForgeFrontierExportTests(unittest.TestCase):
    def test_creates_godot_project_overlay(self):
        candidate = source_scene()
        files = emit_frontier_godot_overlay(
            candidate, cloud_path_duration_s=6, cloud_step_s=1
        )
        self.assertEqual(set(files), {
            "frontier/frontier_scene.tscn",
            "frontier/frontier_scene.gd",
            "frontier/data/scene.json",
        })
        self.assertIn('type="Node3D"', files["frontier/frontier_scene.tscn"])
        self.assertIn("Engine.max_fps", files["frontier/frontier_scene.gd"])
        data = json.loads(files["frontier/data/scene.json"])
        self.assertEqual(data["origin_candidate_digest"], candidate.manifest_digest)
        self.assertEqual(data["requested_fps"], 120)
        self.assertEqual(data["game_era"], "early_3d")
        self.assertTrue(data["world"]["sky_island"] or
                        data["world"]["sky_island"] is False)
        self.assertEqual(len(data["geometry"]["triangles"]),
                         candidate.manifest["render"]["triangle_count"])
        self.assertEqual(len(data["colliders"]), 1)
        self.assertEqual(len(data["clouds"][0]["samples"]), 7)
        self.assertNotEqual(data["clouds"][0]["samples"][0]["x_m"],
                            data["clouds"][0]["samples"][-1]["x_m"])
        self.assertEqual(data["admission"], "candidate_only_not_godot_verified")

    def test_exact_custody_rejects_tampered_manifest(self):
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(
                replace(source_scene(), manifest_digest="a" * 64))

    def test_rejects_invalid_cloud_bake_duration(self):
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(
                source_scene(), cloud_path_duration_s=7, cloud_step_s=2)

    def test_repeatable_export_with_wind_seed(self):
        a = emit_frontier_godot_overlay(source_scene())
        b = emit_frontier_godot_overlay(source_scene())
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
