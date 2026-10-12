"""Executable, source-bound maritime gameplay and adversarial receipt checks."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_sailing_runtime import (
    ACTIONS, SailingActionError, default_layout, normalize_layout, start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, AdvancedRuntimeError,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import (
    catalog, make_editor_document, SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


VOYAGE = (
    ("load",) * 3 + ("undock",) + ("row",) * 9 +
    ("starboard",) + ("row",) * 2 + ("rescue",) +
    ("port",) + ("row",) * 4 + ("starboard",) +
    ("row",) * 5 + ("dock", "deliver")
)


class AdvancedMaritimeTests(unittest.TestCase):
    @staticmethod
    def rules(**overrides):
        return {"dynamic_currents": False, "pirate_speed": 0, **overrides}

    def test_advanced_editor_is_not_authoring_only(self):
        self.assertIn("sailing", ENGINES)
        self.assertEqual(set(ACTION_HELP["sailing"]), set(ACTIONS))
        spec = next(x for x in catalog() if x["id"] == "sailing")
        self.assertEqual(spec["progression_floor"], "advanced")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]), 30)

    def test_original_scene_receipt_and_seed_are_authoritative(self):
        for seed in (0, 1, 19):
            scene = make_advanced_scene("sailing", seed=seed)
            self.assertEqual(validate_advanced_scene(scene), scene)
            result = run_advanced_session("sailing", seed=seed, scene=scene)
            self.assertTrue(verify_advanced_session(result))
            self.assertEqual(result["state"]["position"], scene["layout"]["home"])
            self.assertFalse(result["native_hardware_verified"])
            self.assertFalse(result["publication_certified"])

    def test_real_cargo_and_rescue_victory_by_physical_navigation(self):
        cfg = self.rules()
        scene = make_advanced_scene("sailing", cfg)
        result = run_advanced_session("sailing", cfg, VOYAGE, scene=scene)
        self.assertTrue(verify_advanced_session(result, cfg))
        state = result["state"]
        self.assertTrue(state["finished"])
        self.assertFalse(state["failed"])
        self.assertEqual(state["position"], [15, 9])
        self.assertEqual(state["warehouse"], 0)
        self.assertEqual(state["cargo"], 0)
        self.assertEqual(state["delivered"], 3)
        self.assertEqual(state["destination_stock"], 3)
        self.assertEqual(state["passengers_ashore"], 1)
        self.assertEqual(state["rescued"], 0)
        self.assertIn("earned_original_maritime_expedition", state["events"])
        self.assertEqual(len(result["trace"]), len(VOYAGE))

    def test_endless_play_milestone_does_not_forge_terminal_screen(self):
        cfg = self.rules(completion_mode="endless")
        result = run_advanced_session("sailing", cfg, VOYAGE)
        self.assertFalse(result["terminal"])
        self.assertIn("open_sea_milestone", result["state"]["milestones"])
        continued = run_advanced_session("sailing", cfg, VOYAGE + ("undock",))
        self.assertTrue(verify_advanced_session(continued, cfg))

    def test_no_cargo_out_of_nothing_and_no_port_economy_teleport(self):
        cfg = self.rules(cargo_capacity=2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, ("load",) * 3)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, ("deliver",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, ("undock", "load"))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, ("undock", "dock"))

    def test_real_hull_collision_and_paid_repairs(self):
        cfg = self.rules()
        voyage = ("undock", "port", "row", "row", "row")
        state = run_advanced_session("sailing", cfg, voyage)["state"]
        self.assertEqual(state["position"], [2, 0])
        self.assertEqual(state["collisions"], 1)
        self.assertEqual(state["hull"], cfg.get("hull_integrity", 100) -
                         make_editor_document("sailing", cfg)["settings"]["collision_damage"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, voyage + ("repair",))
        # A review-proved source can put an underwater hazard on a reachable cell.
        layout = default_layout(make_editor_document("sailing", cfg)["settings"], 0)
        layout["reefs"] = [[3, 2]]
        scene = make_advanced_scene("sailing", cfg, layout=layout)
        hit = run_advanced_session("sailing", cfg, ("undock", "row"), scene=scene)
        self.assertIn("reef_scraped_hull", hit["state"]["events"])
        self.assertLess(hit["state"]["hull"], 100)

    def test_finite_supply_and_weather_are_not_decorative(self):
        cfg = self.rules(starting_supplies=1, ration_period=1, starvation_damage=4,
                         hull_integrity=8)
        result = run_advanced_session("sailing", cfg, ("undock", "wait", "wait"))
        self.assertTrue(result["state"]["failed"])
        self.assertEqual(result["state"]["hull"], 0)
        self.assertEqual(result["state"]["supplies"], 0)
        self.assertIn("vessel_lost", result["state"]["events"])
        storm = self.rules(sea_state=12, storm_damage=5, weather_period=2)
        result = run_advanced_session("sailing", storm,
                                      ("undock", "full_sails", "sail", "sail", "sail"), seed=3)
        self.assertGreaterEqual(result["state"]["weather_damage"], 0)
        self.assertTrue(verify_advanced_session(result, storm))

    def test_finite_shoal_and_fishing_gear_no_infinite_food(self):
        cfg = self.rules(fishing_gear=1, fishing_yield=2)
        layout = default_layout(make_editor_document("sailing", cfg)["settings"], 0)
        layout["shoals"] = [[3, 2]]
        scene = make_advanced_scene("sailing", cfg, layout=layout)
        result = run_advanced_session("sailing", cfg, ("undock", "row", "fish"), scene=scene)
        self.assertEqual(result["state"]["fishing_stock"], [2])
        self.assertEqual(result["state"]["fishing_gear"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, ("undock", "row", "fish", "fish"),
                                 scene=scene)

    def test_illegal_scene_geometry_and_stale_configuration_rejected(self):
        cfg = self.rules()
        layout = default_layout(make_editor_document("sailing", cfg)["settings"], 0)
        layout["islands"] += [layout["home"]]
        with self.assertRaises(SceneError):
            make_advanced_scene("sailing", cfg, layout=layout)
        scene = make_advanced_scene("sailing", cfg)
        altered = deepcopy(scene)
        altered["layout"]["warehouse"] = 12
        with self.assertRaises(SceneError):
            validate_advanced_scene(altered, cfg)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", cfg, scene=scene, seed=1)

    def test_client_cannot_forge_victory_damage_money_or_history(self):
        cfg = self.rules()
        report = run_advanced_session("sailing", cfg, ("load", "undock", "row"))
        for edit in ("coins", "hull", "finished", "delivered", "position"):
            tampered = deepcopy(report)
            tampered["state"][edit] = (
                [15, 9] if edit == "position" else
                True if edit == "finished" else 99999
            )
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(tampered, cfg)
        edited = deepcopy(report)
        edited["trace"][1]["digest"] = "0" * 64
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(edited, cfg)

    def test_roundtrip_assembled_scene_proof(self):
        cfg = self.rules()
        doc = make_editor_document("sailing", cfg)
        scene = make_advanced_scene("sailing", cfg)
        assembled = compile_system_assembly(
            "maritime_game", [doc], authorized=True, scenes=[scene]
        )
        self.assertIn("sailing", str(assembled))
        self.assertNotIn("native_hardware_verified': True", str(assembled))

    def test_invalid_commands_and_unsupported_settings_fail_closed(self):
        with self.assertRaises(SystemEditorError):
            make_editor_document("sailing", {"pirate_damage": "0"})
        with self.assertRaises(SystemEditorError):
            make_editor_document("sailing", {"authorizes_magic_warp": True})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", actions=("teleport:15:9",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sailing", actions=("row",))


if __name__ == "__main__":
    unittest.main()
