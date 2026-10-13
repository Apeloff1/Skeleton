"""Original advanced vessel variants, maritime hazards and earned trade routes."""
import unittest
from copy import deepcopy
from skeleton.ai.game_builder.system_editors import catalog, make_editor_document, SystemEditorError
from skeleton.ai.game_builder.advanced_sailing_runtime import (
    ACTIONS, VESSELS, SailingActionError, default_layout, normalize_layout,
    start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, run_advanced_session, verify_advanced_session,
    AdvancedRuntimeError,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)


class MaritimeEngineTests(unittest.TestCase):
    def test_three_vessel_classes_are_playable_not_authoring_only(self):
        self.assertIn("sailing", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["sailing"]))
        spec = next(e for e in catalog() if e["id"] == "sailing")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]), 30)
        self.assertEqual(set(VESSELS), {"skiff", "sloop", "schooner"})

    def test_three_vessels_have_distinct_finite_physics(self):
        results = []
        for name in VESSELS:
            cfg = {"vessel_class": name, "dynamic_currents": False}
            proof = run_advanced_session("sailing", cfg, ["coast"] * 4, seed=0)
            self.assertTrue(verify_advanced_session(proof, cfg))
            state = proof["state"]
            results.append((state["speed"], state["x"]))
        self.assertEqual(len(set(results)), len(VESSELS))

    def test_original_chart_bound_to_exact_settings_and_weather(self):
        for seed in (0, 1, 2, 3, 81):
            rules = make_editor_document("sailing")["settings"]
            layout = default_layout(rules, seed)
            self.assertEqual(normalize_layout(rules, layout), layout)
            scene = make_advanced_scene("sailing", seed=seed)
            self.assertEqual(validate_advanced_scene(scene), scene)
            proof = run_advanced_session("sailing", scene=scene, seed=seed)
            self.assertTrue(verify_advanced_session(proof))
            self.assertFalse(proof["publication_certified"])
            self.assertFalse(proof["native_hardware_verified"])

    def test_cargo_delivery_requires_physical_buoys_and_safe_dock(self):
        cfg = {"wind_speed": 30, "sail_area": 100, "dynamic_currents": False,
               "route_length": 40, "harbor_length": 12, "max_speed": 9,
               "safe_dock_speed": 5, "launch_speed": 3, "sea_state": 0,
               "draft": 1}
        actions = []
        for _ in range(55):
            state = run_advanced_session("sailing", cfg, actions)["state"]
            if state["x"] >= state["harbor_start"] and state["anchor"]:
                actions.append("dock")
                break
            if state["x"] >= state["harbor_start"] and not state["anchor"]:
                actions.append("drop_anchor")
            elif state["x"] >= state["harbor_start"] - 6 and state["sails"]:
                actions.append("lower")
            else:
                actions.append("coast")
        proof = run_advanced_session("sailing", cfg, actions)
        self.assertTrue(proof["state"]["finished"])
        self.assertFalse(proof["state"]["failed"])
        self.assertEqual(proof["state"]["cargo_delivered"], 20)
        self.assertEqual(len(proof["state"]["buoys_seen"]), 2)
        self.assertTrue(verify_advanced_session(proof, cfg))

    def test_no_false_terminal_event_or_unearned_repair(self):
        cfg = make_editor_document("sailing")["settings"]
        state = start(cfg, 0)
        step(state, cfg, "dock")
        self.assertFalse(state["finished"])
        self.assertIn("harbor_docking_refused", state["events"])
        with self.assertRaises(SailingActionError):
            step(state, cfg, "teleport_to_port")
        with self.assertRaises(SailingActionError):
            step(state, cfg, "repair")

    def test_forged_chart_and_status_are_rejected(self):
        scene = make_advanced_scene("sailing", seed=0)
        edited = deepcopy(scene)
        edited["layout"]["cargo_manifest"] += 100
        with self.assertRaises(SceneError):
            validate_advanced_scene(edited)
        proof = run_advanced_session("sailing", actions=["coast", "trim_in"])
        tampered = deepcopy(proof)
        tampered["state"]["cargo_delivered"] = 99
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(tampered)

    def test_unsafe_cargo_and_harbor_settings_rejected(self):
        for values in (
            {"cargo_contract": 200, "cargo_capacity": 20},
            {"route_length": 40, "harbor_length": 20},
            {"max_speed": 3, "launch_speed": 15},
            {"max_speed": 3, "safe_dock_speed": 10},
            {"vessel_class": "unlicensed_ship"},
            {"dynamic_currents": 1},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("sailing", values)


if __name__ == "__main__":
    unittest.main()
