"""Advanced original physics gameplay, full replay, hazards, and authoring custody."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_runtime import (
    ACTIONS, PhysicsActionError, default_layout, normalize_layout, start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    SavegameError, export_advanced_savegame, import_advanced_savegame,
    continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editors import (
    catalog, make_editor_document, SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class AdvancedOriginalPhysicsTests(unittest.TestCase):
    def cfg(self, **changes):
        return make_editor_document("physics", changes)["settings"]

    def scene(self, values=None, layout=None, seed=0):
        return make_advanced_scene("physics", values, seed=seed, layout=layout)

    def test_editor_has_real_runtime_and_all_registered_actions(self):
        self.assertIn("physics", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["physics"]))
        self.assertEqual(len(ACTIONS), len(set(ACTIONS)))
        spec = next(value for value in catalog() if value["id"] == "physics")
        self.assertEqual(spec["progression_floor"], "advanced")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertEqual(len(spec["fields"]), 40)

    def test_default_2d_world_produces_authoritative_replay_receipts(self):
        for seed in (0, 1, 99):
            scene = self.scene(seed=seed)
            self.assertEqual(scene, validate_advanced_scene(scene))
            report = run_advanced_session("physics", scene=scene, seed=seed,
                                          actions=("inspect", "push:east", "step:4"))
            self.assertTrue(verify_advanced_session(report))
            self.assertEqual(report["state"]["depth"], 1)
            self.assertEqual(report["state"]["frame"], 6)
            self.assertFalse(report["native_hardware_verified"])
            self.assertFalse(report["publication_certified"])

    def test_original_3d_game_has_actual_third_axis_and_spatial_bounds(self):
        cfg = {"dimension": "3d"}
        scene = self.scene(cfg)
        report = run_advanced_session("physics", cfg,
                                      ("push:front", "step"), scene=scene)
        self.assertEqual(report["state"]["depth"], 3)
        self.assertGreater(report["state"]["bodies"][0]["position"][2], 100)
        self.assertTrue(verify_advanced_session(report, cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", actions=("push:front",))

    def test_source_bound_goal_is_earned_by_real_motion_not_spawn_or_client_flag(self):
        cfg = {"goal_radius": 70, "goal_speed": 300}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["goal"] = [300, 960, 0]
        scene = self.scene(cfg, layout)
        no_progress = run_advanced_session("physics", cfg, scene=scene)
        self.assertFalse(no_progress["terminal"])
        earned = run_advanced_session("physics", cfg, ("push:east",), scene=scene)
        self.assertTrue(earned["terminal"])
        self.assertTrue(earned["state"]["finished"])
        self.assertGreater(earned["state"]["bodies"][0]["position"][0], 200)
        self.assertIn("original_physical_cargo_docked", earned["state"]["events"])
        self.assertTrue(verify_advanced_session(earned, cfg))
        layout["goal"] = [200, 960, 0]
        with self.assertRaises(SceneError):
            self.scene(cfg, layout)

    def test_original_sandbox_milestone_does_not_end_play(self):
        cfg = {"goal_radius": 70, "goal_speed": 300, "completion_mode": "sandbox"}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["goal"] = [300, 960, 0]
        scene = self.scene(cfg, layout)
        report = run_advanced_session("physics", cfg,
                                      ("push:east", "inspect"), scene=scene)
        self.assertFalse(report["terminal"])
        self.assertIn("cargo_docked", report["state"]["milestones"])
        self.assertTrue(verify_advanced_session(report, cfg))

    def test_finite_impulse_budget_and_velocity_clamp(self):
        cfg = {"impulse_budget": 1, "speed_limit": 30}
        result = run_advanced_session("physics", cfg, ("push:east",))
        self.assertEqual(result["state"]["impulses_left"], 0)
        self.assertLessEqual(max(abs(x) for x in result["state"]["bodies"][0]["velocity"]), 30)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", cfg, ("push:east", "push:east"))

    def test_collision_world_bounds_and_real_static_fixture(self):
        report = run_advanced_session("physics", {"impulse_strength": 500},
                                      ("push:west",) * 12)
        self.assertGreater(report["state"]["contacts"], 0)
        self.assertGreaterEqual(report["state"]["bodies"][0]["position"][0], 40)
        cfg = {"impulse_strength": 300}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["fixtures"] = [
            {"position": [430, 900, 0], "half_size": [30, 100, 40], "layer": 3}
        ]
        scene = self.scene(cfg, layout)
        world = run_advanced_session("physics", cfg,
                                     ("push:east",) * 5, scene=scene)["state"]
        self.assertGreater(world["contacts"], 0)
        self.assertLessEqual(world["bodies"][0]["position"][0], 430)

    def test_rope_attach_requires_proximity_and_genuine_tension(self):
        report = run_advanced_session("physics", actions=("attach:0", "push:east", "step:4"))
        self.assertTrue(verify_advanced_session(report))
        self.assertIn("rope", report["state"])
        self.assertEqual(report["state"]["rope"]["anchor"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", {"attach_range": 100}, ("attach:0",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", actions=("detach",))

    def test_finite_motors_spend_real_energy(self):
        cfg = {"initial_battery": 3}
        report = run_advanced_session("physics", cfg, ("fan:on", "step:4"))
        self.assertEqual(report["state"]["battery"], 0)
        self.assertGreater(report["state"]["motors_used"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", {"initial_battery": 0}, ("magnet:on",))
        powered = run_advanced_session("physics", cfg, ("magnet:on", "inspect"))
        self.assertLess(powered["state"]["battery"], 3)

    def test_material_and_collision_masks_are_actual_authoritative_sources(self):
        cfg = {"gravity": 0, "impulse_strength": 450}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["bodies"][1]["position"] = [390, 960, 0]
        layout["bodies"][1]["velocity"] = [0, 0, 0]
        scene = self.scene(cfg, layout)
        contact = run_advanced_session("physics", cfg, ("push:east",) * 4, scene=scene)
        self.assertGreater(contact["state"]["contacts"], 0)
        layout["bodies"][1]["mask"] = 2  # Counterweight does not accept payload layer 1.
        isolated = self.scene(cfg, layout)
        no_contact = run_advanced_session("physics", cfg,
                                          ("push:east",) * 4, scene=isolated)
        self.assertLess(no_contact["state"]["contacts"], contact["state"]["contacts"])

    def test_fluid_submersion_consumes_momentum_and_source_buoyancy(self):
        cfg = {"buoyancy": 1500, "water_drag": 80}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["water_y"] = layout["floor_y"]
        scene = self.scene(cfg, layout)
        water = run_advanced_session("physics", cfg, ("push:east", "step"), scene=scene)
        dry = run_advanced_session("physics", cfg, ("push:east", "step"))
        self.assertGreater(water["state"]["water_contacts"], 0)
        self.assertLess(abs(water["state"]["bodies"][0]["velocity"][0]),
                        abs(dry["state"]["bodies"][0]["velocity"][0]))

    def test_strict_scene_rejects_overlap_unsafe_geometry_and_axis_forgery(self):
        cfg = self.cfg()
        layout = default_layout(cfg, 0)
        layout["bodies"][1]["id"] = "payload"
        with self.assertRaises(SceneError):
            self.scene(layout=layout)
        layout = default_layout(cfg, 0)
        layout["fixtures"][0]["position"] = layout["bodies"][0]["position"]
        with self.assertRaises(SceneError):
            self.scene(layout=layout)
        layout = default_layout(cfg, 0)
        layout["bodies"][0]["position"][2] = 100
        with self.assertRaises(SceneError):
            self.scene(layout=layout)
        layout = default_layout(cfg, 0)
        layout["secret_code"] = "script:touch"
        with self.assertRaises(SceneError):
            self.scene(layout=layout)

    def test_invalid_type_and_resource_boundaries_fail_closed(self):
        with self.assertRaises(SystemEditorError):
            make_editor_document("physics", {"gravity": True})
        with self.assertRaises(SystemEditorError):
            make_editor_document("physics", {"solver_iterations": 999})
        with self.assertRaises(SystemEditorError):
            make_editor_document("physics", {"unknown_executable_rule": "grant victory"})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", actions=("teleport:payload:goal",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", actions=("select:3",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", actions=("push:front",))

    def test_scene_hash_and_replay_reject_edited_physical_outcomes(self):
        scene = self.scene()
        result = run_advanced_session("physics", actions=("push:east", "step:4"), scene=scene)
        for field, value in (
            ("position", [800, 960, 0]), ("mass", 1), ("broken", True)
        ):
            fake = deepcopy(result)
            fake["state"]["bodies"][0][field] = value
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(fake)
        forged = deepcopy(scene)
        forged["layout"]["goal"] = [200, 960, 0]
        with self.assertRaises(SceneError):
            validate_advanced_scene(forged)

    def test_save_resume_and_tamper_resistance(self):
        base = run_advanced_session("physics", actions=("push:east", "step"))
        save = export_advanced_savegame(base)
        self.assertEqual(import_advanced_savegame(save)["session"], base)
        continued = continue_advanced_savegame(save, ("step:4",))
        verified = import_advanced_savegame(continued)
        self.assertGreater(verified["session"]["state"]["frame"], base["state"]["frame"])
        fake = deepcopy(save)
        fake["actions"].append("push:east")
        with self.assertRaises(SavegameError):
            import_advanced_savegame(fake)

    def test_source_assembly_runs_independent_base_and_scene_smokes(self):
        doc = make_editor_document("physics")
        scene = self.scene()
        assembly = compile_system_assembly("original_physics", [doc],
                                           authorized=True, scenes=[scene])
        self.assertEqual(assembly["source_system_count"], 1)
        self.assertEqual(assembly["authored_scene_count"], 1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"], "physics")
        self.assertFalse(assembly["ready_for_release"])


    def test_high_speed_moving_object_cannot_tunnel_through_thin_fixture(self):
        cfg = {"impulse_strength": 500, "speed_limit": 400}
        layout = default_layout(self.cfg(**cfg), 0)
        layout["fixtures"] = [
            {"position": [430, 900, 0], "half_size": [10, 100, 40],
             "layer": 3}
        ]
        scene = self.scene(cfg, layout)
        report = run_advanced_session(
            "physics", cfg, ("push:east", "push:east"), scene=scene
        )
        self.assertTrue(verify_advanced_session(report, cfg))
        self.assertTrue(any("swept_fixture_contact" in frame["events"]
                            for frame in report["trace"]))
        self.assertLess(report["state"]["bodies"][0]["position"][0], 430)

    def test_one_body_resource_configuration_runs_without_phantom_crates(self):
        cfg = {"max_bodies": 1}
        scene = self.scene(cfg)
        report = run_advanced_session("physics", cfg, ("inspect", "push:east"), scene=scene)
        self.assertEqual(len(report["state"]["bodies"]), 1)
        self.assertTrue(verify_advanced_session(report, cfg))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics", cfg, ("select:1",), scene=scene)

    def test_six_eight_selectors_admit_only_real_reviewed_body_ids(self):
        cfg = self.cfg()
        layout = default_layout(cfg, 0)
        for idx in range(2, 8):
            layout["bodies"].append({
                "id": "body_" + str(idx),
                "position": [200 + idx*140, 500, 0],
                "velocity": [0, 0, 0],
                "radius": 20,
                "mass": idx+1,
                "material": "rubber",
                "layer": 2,
                "mask": 3,
                "break_threshold": 400,
            })
        scene = self.scene(layout=layout)
        result = run_advanced_session(
            "physics", actions=("select:7", "push:east"), scene=scene
        )
        self.assertEqual(result["state"]["selected"], 7)
        self.assertTrue(verify_advanced_session(result))


if __name__ == "__main__":
    unittest.main()
