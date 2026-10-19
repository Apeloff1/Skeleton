"""Materialized signed-GDD native Godot smoke project source verification."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_game_frontier_smoke import build_smoke_project


class NativeGodotProjectMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)

    def test_multiactor_source_generates_valid_forge_godot_tree(self):
        for fps in (30,50,60,120):
            target=self.path/f"smoke-{fps}"
            target.mkdir()
            summary=build_smoke_project(target,fps=fps,frames=24)
            self.assertEqual(summary["actors"],2)
            self.assertEqual(summary["fps"],fps)
            scene=json.loads((target/"frontier/data/scene.json").read_text())
            config=scene["native_capture"]
            self.assertEqual(config["fps"],fps)
            self.assertTrue(config["enabled"])
            self.assertEqual(config["max_frames"],24)
            self.assertEqual(len(config["actors"]),2)
            self.assertEqual(config["actor_id"],"hero")
            self.assertEqual(config["candidate_digest"],
                             scene["origin_candidate_digest"])
            script=(target/"frontier/frontier_scene.gd").read_text()
            self.assertIn("_record_native_physics()",script)
            self.assertIn("native_chunks",script)
            self.assertIn("generated_source_proxy",script)
            self.assertIn('user://frontier_native_physics.jsonl',script)
            self.assertTrue((target/"frontier/frontier_scene.tscn").is_file())
            self.assertTrue((target/"project.godot").is_file())
            bible=json.loads((target/"signed_gdd.json").read_text())
            self.assertIn("world",bible)

    def test_refuses_overwrite_and_bounded_frame_rate(self):
        target=self.path/"authorized"
        target.mkdir()
        build_smoke_project(target)
        with self.assertRaises(ValueError):
            build_smoke_project(target)
        separate=self.path/"other"
        separate.mkdir()
        with self.assertRaises(ValueError):
            build_smoke_project(separate,fps=144)
        with self.assertRaises(ValueError):
            build_smoke_project(separate,frames=10_000)

    def test_nonexistent_or_symlink_output_is_not_accepted(self):
        with self.assertRaises(ValueError):
            build_smoke_project(self.path/"not-created")
        actual=self.path/"base"
        actual.mkdir()
        indirect=self.path/"linked"
        indirect.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(ValueError):
            build_smoke_project(indirect)


if __name__=="__main__":
    unittest.main()

    def test_native_reference_controls_from_real_exporter(self):
        import json
        from skeleton.jeeves.game_frontier import compile_frontier_scene
        from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd, FrameObject
        from skeleton.jeeves.game_frontier_production import Vec3
        from skeleton.forge.game_frontier_godot import (
            emit_frontier_godot_overlay, FrontierGodotError,
        )
        from tests.test_game_frontier_position_frames import gdd
        from tests.test_game_frontier_advanced_scene import scene_params
        params=scene_params()
        params.update(frame_gdd=bind_signed_gdd(gdd()),frame_index=0,
            frame_objects=(FrameObject("hero",Vec3(0,0,30),
                                      Vec3(0,0,-20),"a"*64),))
        candidate=compile_frontier_scene(**params)
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(candidate,
                enable_native_reference_controls=True)
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(candidate,
                native_reference_test_drive_ticks=5)
        payload=emit_frontier_godot_overlay(
            candidate,enable_native_capture=True,
            enable_native_reference_controls=True,
            native_reference_test_drive_ticks=5)
        scene=json.loads(payload["frontier/data/scene.json"])
        self.assertTrue(scene["native_capture"]["reference_controls"]["enabled"])
        self.assertEqual(scene["native_capture"]["reference_controls"][
            "headless_fixture_ticks"],5)
        script=payload["frontier/frontier_scene.gd"]
        self.assertIn('Input.get_vector("ui_left", "ui_right"',script)
        self.assertIn("apply_central_impulse",script)
        self.assertIn("bounded_reference_controller_not_NPC_AI",script)

    def test_native_overlay_live_event_inspector_camera_and_speed_controls(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            folder=Path(root)
            build_smoke_project(folder,fps=60,frames=20)
            scene=json.loads((folder/"frontier/data/scene.json").read_text())
            self.assertTrue(scene["native_capture"]["reference_controls"]["camera_follow"])
            source=(folder/"frontier/frontier_scene.gd").read_text()
            for expected in ("NativeGameplayEventInspector",
                             "_native_recent_zone_events", "KEY_P",
                             "KEY_MINUS", "KEY_EQUAL", "Engine.time_scale",
                             "_native_camera.global_position.lerp"):
                self.assertIn(expected,source)
