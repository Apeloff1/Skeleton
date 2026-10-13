"""Executable, source-bound maritime gameplay and adversarial receipt checks."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_maritime_rescue_runtime import (
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
        self.assertIn("maritime_rescue", ENGINES)
        self.assertEqual(set(ACTION_HELP["maritime_rescue"]), set(ACTIONS))
        spec = next(x for x in catalog() if x["id"] == "maritime_rescue")
        self.assertEqual(spec["progression_floor"], "advanced")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]), 30)

    def test_original_scene_receipt_and_seed_are_authoritative(self):
        for seed in (0, 1, 19):
            scene = make_advanced_scene("maritime_rescue", seed=seed)
            self.assertEqual(validate_advanced_scene(scene), scene)
            result = run_advanced_session("maritime_rescue", seed=seed, scene=scene)
            self.assertTrue(verify_advanced_session(result))
            self.assertEqual(result["state"]["position"], scene["layout"]["home"])
            self.assertFalse(result["native_hardware_verified"])
            self.assertFalse(result["publication_certified"])

    def test_real_cargo_and_rescue_victory_by_physical_navigation(self):
        cfg = self.rules()
        scene = make_advanced_scene("maritime_rescue", cfg)
        result = run_advanced_session("maritime_rescue", cfg, VOYAGE, scene=scene)
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
        result = run_advanced_session("maritime_rescue", cfg, VOYAGE)
        self.assertFalse(result["terminal"])
        self.assertIn("open_sea_milestone", result["state"]["milestones"])
        continued = run_advanced_session("maritime_rescue", cfg, VOYAGE + ("undock",))
        self.assertTrue(verify_advanced_session(continued, cfg))

    def test_no_cargo_out_of_nothing_and_no_port_economy_teleport(self):
        cfg = self.rules(cargo_capacity=2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("load",) * 3)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("deliver",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("undock", "load"))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("undock", "dock"))

    def test_real_hull_collision_and_paid_repairs(self):
        cfg = self.rules()
        voyage = ("undock", "port", "row", "row", "row")
        state = run_advanced_session("maritime_rescue", cfg, voyage)["state"]
        self.assertEqual(state["position"], [2, 0])
        self.assertEqual(state["collisions"], 1)
        self.assertEqual(state["hull"], cfg.get("hull_integrity", 100) -
                         make_editor_document("maritime_rescue", cfg)["settings"]["collision_damage"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, voyage + ("repair",))
        # A review-proved source can put an underwater hazard on a reachable cell.
        layout = default_layout(make_editor_document("maritime_rescue", cfg)["settings"], 0)
        layout["reefs"] = [[3, 2]]
        scene = make_advanced_scene("maritime_rescue", cfg, layout=layout)
        hit = run_advanced_session("maritime_rescue", cfg, ("undock", "row"), scene=scene)
        self.assertIn("reef_scraped_hull", hit["state"]["events"])
        self.assertLess(hit["state"]["hull"], 100)

    def test_finite_supply_and_weather_are_not_decorative(self):
        cfg = self.rules(starting_supplies=1, ration_period=1, starvation_damage=4,
                         hull_integrity=8)
        result = run_advanced_session("maritime_rescue", cfg, ("undock", "wait", "wait"))
        self.assertTrue(result["state"]["failed"])
        self.assertEqual(result["state"]["hull"], 0)
        self.assertEqual(result["state"]["supplies"], 0)
        self.assertIn("vessel_lost", result["state"]["events"])
        storm = self.rules(sea_state=12, storm_damage=5, weather_period=2)
        result = run_advanced_session("maritime_rescue", storm,
                                      ("undock", "full_sails", "sail", "sail", "sail"), seed=3)
        self.assertGreaterEqual(result["state"]["weather_damage"], 0)
        self.assertTrue(verify_advanced_session(result, storm))

    def test_finite_shoal_and_fishing_gear_no_infinite_food(self):
        cfg = self.rules(fishing_gear=1, fishing_yield=2)
        layout = default_layout(make_editor_document("maritime_rescue", cfg)["settings"], 0)
        layout["shoals"] = [[3, 2]]
        scene = make_advanced_scene("maritime_rescue", cfg, layout=layout)
        result = run_advanced_session("maritime_rescue", cfg, ("undock", "row", "fish"), scene=scene)
        self.assertEqual(result["state"]["fishing_stock"], [2])
        self.assertEqual(result["state"]["fishing_gear"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("undock", "row", "fish", "fish"),
                                 scene=scene)

    def test_illegal_scene_geometry_and_stale_configuration_rejected(self):
        cfg = self.rules()
        layout = default_layout(make_editor_document("maritime_rescue", cfg)["settings"], 0)
        layout["islands"] += [layout["home"]]
        with self.assertRaises(SceneError):
            make_advanced_scene("maritime_rescue", cfg, layout=layout)
        scene = make_advanced_scene("maritime_rescue", cfg)
        altered = deepcopy(scene)
        altered["layout"]["warehouse"] = 12
        with self.assertRaises(SceneError):
            validate_advanced_scene(altered, cfg)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, scene=scene, seed=1)

    def test_client_cannot_forge_victory_damage_money_or_history(self):
        cfg = self.rules()
        report = run_advanced_session("maritime_rescue", cfg, ("load", "undock", "row"))
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
        doc = make_editor_document("maritime_rescue", cfg)
        scene = make_advanced_scene("maritime_rescue", cfg)
        assembled = compile_system_assembly(
            "maritime_game", [doc], authorized=True, scenes=[scene]
        )
        self.assertIn("maritime_rescue", str(assembled))
        self.assertNotIn("native_hardware_verified': True", str(assembled))

    def test_invalid_commands_and_unsupported_settings_fail_closed(self):
        with self.assertRaises(SystemEditorError):
            make_editor_document("maritime_rescue", {"pirate_damage": "0"})
        with self.assertRaises(SystemEditorError):
            make_editor_document("maritime_rescue", {"authorizes_magic_warp": True})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", actions=("teleport:15:9",))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", actions=("row",))


    def test_rescue_only_requires_no_fabricated_cargo_sale(self):
        cfg = self.rules(mission_type="rescue")
        route = (
            ("undock",) + ("row",) * 9 + ("starboard",) + ("row",) * 2 +
            ("rescue", "port") + ("row",) * 4 + ("starboard",) +
            ("row",) * 5 + ("dock", "disembark")
        )
        result = run_advanced_session("maritime_rescue", cfg, route)
        self.assertTrue(result["terminal"])
        self.assertTrue(result["state"]["finished"])
        self.assertEqual(result["state"]["delivered"], 0)
        self.assertEqual(result["state"]["passengers_ashore"], 1)
        self.assertEqual(result["state"]["warehouse"], 3)
        self.assertTrue(verify_advanced_session(result, cfg))

    def test_buoyancy_ingress_and_real_paid_bilge_work(self):
        cfg = self.rules(hull_integrity=40, collision_damage=15,
                         leak_threshold=3, pump_capacity=20)
        damaged = ("undock", "port", "row", "row", "row", "wait")
        before = run_advanced_session("maritime_rescue", cfg, damaged)["state"]
        after = run_advanced_session("maritime_rescue", cfg, damaged + ("pump",))["state"]
        self.assertGreater(before["flooding"], after["flooding"])
        self.assertEqual(after["pumps_used"], 1)
        self.assertLess(after["supplies"], before["supplies"])
        self.assertEqual(after["hull"], before["hull"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maritime_rescue", cfg, ("pump",))

    def test_flotation_limit_prevents_weightless_forged_cargo(self):
        cfg = self.rules(buoyancy_capacity=40, overload_damage=5)
        loaded = run_advanced_session("maritime_rescue", cfg, ("load", "load", "load"))
        state = loaded["state"]
        self.assertLess(state["buoyancy_margin"], 0)
        self.assertGreater(state["displacement"], 40)
        self.assertLess(state["hull"], 100)

    def test_savegame_replay_and_continuation_rejects_forged_inventories(self):
        from skeleton.ai.game_builder.advanced_gameplay_save import (
            SavegameError, export_advanced_savegame, import_advanced_savegame,
            continue_advanced_savegame,
        )
        cfg = self.rules()
        original = run_advanced_session("maritime_rescue", cfg, ("load", "undock", "row"))
        saved = export_advanced_savegame(original, cfg)
        imported = import_advanced_savegame(saved)
        self.assertEqual(imported["session"], original)
        continued = continue_advanced_savegame(saved, ("row", "row"))
        self.assertEqual(import_advanced_savegame(continued)["session"]["state"]["position"],
                         [5, 2])
        forged = deepcopy(saved)
        forged["actions"] = ["load", "load", "load", "undock", "row"]
        with self.assertRaises(SavegameError):
            import_advanced_savegame(forged)


if __name__ == "__main__":
    unittest.main()
