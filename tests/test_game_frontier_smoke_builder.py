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
            self.assertIn("_load_approved_native_gameplay",script)
            self.assertIn("_advance_approved_dialogue",script)
            self.assertIn("ApprovedGameDialogueCard",script)
            self.assertIn("ApprovedCinematicCuePanel",script)
            self.assertIn("_next_approved_cue",script)
            self.assertIn("_create_approved_inventory_objects",script)
            self.assertIn("ApprovedInventoryBrowser",script)
            self.assertIn("_cycle_approved_inventory",script)
            self.assertIn("_inspect_approved_npc_proximity",script)
            self.assertIn("_interact_approved_npc",script)
            self.assertIn("frontier_local_npc_interactions.jsonl",script)
            self.assertIn("ApprovedNPCProximityInspector",script)
            self.assertIn("_persist_verified_gameplay_receipt",script)
            self.assertIn("NativeVirtualFlightInstruments",script)
            self.assertIn("frontier_virtual_instruments.jsonl",script)
            self.assertIn("independent_native_instrument_observation_not_attested",script)
            self.assertIn("GameNativeLandingRiskInspector",script)
            self.assertIn("Required native Godot game interface is missing",script)
            self.assertIn("_update_native_landing_risk",script)
            self.assertIn("FictionalWorldRouteBook",script)
            self.assertIn("GodotLiveVirtualGPSDelta",script)
            self.assertIn("_update_live_virtual_gps_delta",script)
            self.assertIn("GameCinematicCameraDirector",script)
            self.assertIn("Overhead inspection",script)
            self.assertIn("_cycle_game_cinematic_camera",script)
            self.assertIn("_cycle_virtual_route_waypoint",script)
            self.assertIn("LiveGameAltimeterCompassVario",script)
            self.assertIn("_update_native_flight_instruments()",script)
            self.assertIn("Existing approved game save differs from replay",script)
            self.assertIn("ApprovedInventoryToken_",script)
            self.assertIn("ContinueApprovedDialogue",script)
            self.assertIn("NativeApprovedGameplayHUD",script)
            self.assertIn("frontier_approved_gameplay_receipt.json",script)
            self.assertIn("Unsupported game world mutation rejected",script)
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

    def test_native_fixture_authors_three_real_runtime_rpg_pages(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages
        with TemporaryDirectory() as root:
            directory=Path(root)
            build_smoke_project(directory,frames=20)
            source=json.loads((directory/"native_rpg_pages.json").read_text())
            authored=parse_native_rpg_pages(source)
            self.assertEqual(len(authored),5)
            self.assertEqual({page.page_id for page in authored},{
                "observed_actor_motion","entered_game_zone","exited_game_zone",
                "begin_sky_trial","complete_sky_trial"})
            self.assertTrue(all(not page.repeat for page in authored))

    def test_native_gameplay_updraft_is_real_engine_applied_force(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from skeleton.jeeves.game_frontier_native_fields import normalize_native_force_fields
        with TemporaryDirectory() as root:
            dest=Path(root)
            build_smoke_project(dest,frames=20)
            source=json.loads((dest/"frontier/data/scene.json").read_text())
            fields=source["native_capture"]["gameplay_force_fields"]
            self.assertEqual(len(fields),1)
            self.assertEqual(fields,normalize_native_force_fields(fields))
            self.assertEqual(fields[0]["actor_id"],"hero")
            self.assertEqual(fields[0]["kind"],"updraft")
            script=(dest/"frontier/frontier_scene.gd").read_text()
            for marker in ("_apply_native_gameplay_fields",
                           "native_force_field_schema",
                           "previous_step_field_forces",
                           "_aero_character.apply_central_force(applied)",
                           "NativeGameForcePreview_", "KEY_F"):
                self.assertIn(marker,script)
