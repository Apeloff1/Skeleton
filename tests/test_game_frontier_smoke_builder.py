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
