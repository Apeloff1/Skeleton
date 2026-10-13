"""Advanced original aircraft game: source, dynamics, replay and landing."""
import unittest
from copy import deepcopy
from skeleton.ai.game_builder.system_editors import make_editor_document, catalog, SystemEditorError
from skeleton.ai.game_builder.advanced_flight_runtime import (
    ACTIONS, MODELS, default_layout, normalize_layout, start, step, FlightActionError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, run_advanced_session, verify_advanced_session,
    AdvancedRuntimeError,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene, SceneError,
)


class FlightTests(unittest.TestCase):
    def test_advanced_configuration_and_signed_level(self):
        self.assertIn("flight", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["flight"]))
        self.assertEqual(len(ACTIONS), len(set(ACTIONS)))
        spec = next(e for e in catalog() if e["id"] == "flight")
        self.assertGreaterEqual(len(spec["fields"]), 30)
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        for seed in (0, 1, 2, 11):
            config = make_editor_document("flight")["settings"]
            self.assertEqual(normalize_layout(config, default_layout(config, seed)),
                             default_layout(config, seed))
            scene = make_advanced_scene("flight", seed=seed)
            self.assertEqual(validate_advanced_scene(scene), scene)
            report = run_advanced_session("flight", seed=seed, scene=scene)
            self.assertTrue(verify_advanced_session(report))
            self.assertFalse(report["native_hardware_verified"])

    def test_three_models_have_distinct_physical_state(self):
        states = []
        for mode in MODELS:
            params = {"flight_model": mode}
            record = run_advanced_session("flight", params,
                                          ["throttle_up", "climb", "coast"], seed=2)
            self.assertTrue(verify_advanced_session(record, params))
            s = record["state"]
            states.append((s["altitude"], s["speed"], s["fuel"], s["lane"]))
        self.assertEqual(len(set(states)), len(MODELS))

    def test_actual_beacon_navigation_and_runway_landing(self):
        params = dict(flight_model="arcade", wind_strength=0, headwind=0,
                      fuel_capacity=500, stall_speed=10, route_length=40,
                      runway_length=12, launch_altitude=10, waypoint_floor=1,
                      waypoint_ceiling=30, landing_altitude=15, landing_speed=130,
                      terrain_height=0, drag=10, mass=20)
        actions = []
        for _ in range(35):
            state = run_advanced_session("flight", params, actions)["state"]
            if state["x"] >= state["runway_start"] and state["gear"]:
                actions.append("land")
                break
            actions.append("gear_down" if state["x"] >= state["runway_start"] - 5
                           and not state["gear"] else "coast")
        proof = run_advanced_session("flight", params, actions)
        self.assertTrue(proof["state"]["finished"])
        self.assertTrue(proof["state"]["landed"])
        self.assertEqual(len(proof["state"]["beacons_seen"]), 2)
        self.assertEqual(proof["state"]["beacons_missed"], [])
        self.assertTrue(verify_advanced_session(proof, params))

    def test_false_victory_and_forged_geometry_are_rejected(self):
        cfg = make_editor_document("flight")["settings"]
        state = start(cfg, 0)
        step(state, cfg, "land")
        self.assertFalse(state["finished"])
        self.assertIn("landing_refused_unmet_conditions", state["events"])
        with self.assertRaises(FlightActionError):
            step(state, cfg, "teleport")
        state["boosts"] = 0
        with self.assertRaises(FlightActionError):
            step(state, cfg, "boost")
        scene = make_advanced_scene("flight")
        bad = deepcopy(scene)
        bad["layout"]["runway_start"] = 0
        with self.assertRaises(SceneError):
            validate_advanced_scene(bad)
        proof = run_advanced_session("flight", actions=["climb"])
        forged = deepcopy(proof)
        forged["state"]["fuel"] += 5
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged)

    def test_invalid_settings_fail_closed(self):
        for values in (
            {"runway_length": 20, "route_length": 40},
            {"landing_speed": 10, "stall_speed": 25},
            {"waypoint_ceiling": 300, "max_altitude": 100},
            {"autopilot": 1},
            {"fuel_capacity": 501},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("flight", values)


if __name__ == "__main__":
    unittest.main()
