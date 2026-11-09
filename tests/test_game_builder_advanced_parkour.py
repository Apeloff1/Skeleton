"""Advanced original traversal: actual hazard physics and witnessed route completion."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_parkour_runtime import (
    ACTIONS, COURSES, ParkourActionError, default_layout, normalize_layout,
    start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP, ENGINES, AdvancedRuntimeError,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.system_editors import (
    catalog, make_editor_document, SystemEditorError,
)


class OriginalParkourTests(unittest.TestCase):
    def test_new_engine_has_real_actions_and_typed_studio_settings(self):
        self.assertIn("parkour", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["parkour"]))
        self.assertEqual(len(ACTIONS), len(set(ACTIONS)))
        spec = next(c for c in catalog() if c["id"] == "parkour")
        self.assertEqual(spec["progression_floor"], "advanced")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]), 40)
        self.assertEqual(len(COURSES), 3)

    def test_all_three_original_courses_have_independent_signed_geometry(self):
        for seed in range(6):
            config = make_editor_document("parkour")["settings"]
            self.assertEqual(normalize_layout(config, default_layout(config, seed)),
                             default_layout(config, seed))
            scene = make_advanced_scene("parkour", seed=seed)
            self.assertEqual(validate_advanced_scene(scene), scene)
            record = run_advanced_session("parkour", scene=scene, seed=seed)
            self.assertTrue(verify_advanced_session(record))
            self.assertFalse(record["native_hardware_verified"])

    def test_technique_clears_real_obstacle_where_running_collides(self):
        clear = run_advanced_session("parkour",
                                     actions=["run"]*3+["jump"], seed=0)
        strike = run_advanced_session("parkour",
                                      actions=["run"]*4, seed=0)
        self.assertTrue(verify_advanced_session(clear))
        self.assertTrue(verify_advanced_session(strike))
        self.assertIn("technique_cleared_gap", clear["state"]["events"])
        self.assertGreater(clear["state"]["x"], strike["state"]["x"])
        self.assertEqual(strike["state"]["falls"], 1)
        self.assertLess(strike["state"]["health"],
                        strike["state"]["max_health"])

    def test_original_proven_safe_course_can_actually_finish(self):
        cfg = make_editor_document("parkour")["settings"]
        layout = default_layout(cfg, 0)
        # Reviewable alternative route: obstacle lane diverted; collect
        # exact, spatially visited medals in the central accessible lane.
        for hazard in layout["obstacles"]:
            hazard["lane"] = 0
        scene = make_advanced_scene("parkour", seed=0, layout=layout)
        proof = run_advanced_session("parkour",
                                     actions=["run"]*25+["finish"], scene=scene)
        self.assertTrue(proof["state"]["finished"])
        self.assertFalse(proof["state"]["failed"])
        self.assertEqual(proof["state"]["medals_collected"],
                         [cfg["course_length"]//3, 2*cfg["course_length"]//3])
        self.assertGreater(proof["state"]["score"], 0)
        self.assertTrue(verify_advanced_session(proof))
        assembled = compile_system_assembly(
            "original_parkour", [make_editor_document("parkour")],
            authorized=True, scenes=[scene])
        self.assertEqual(assembled["authored_scene_count"], 1)
        self.assertEqual(assembled["advanced_runtime_evidence"][0]["editor"], "parkour")

    def test_unearned_finishes_forged_medals_and_teleports_are_rejected(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("parkour", actions=["finish"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("parkour", actions=["teleport"])
        game = run_advanced_session("parkour", actions=["run", "run"])
        tampered = deepcopy(game)
        tampered["state"]["medals_collected"] = [20, 40]
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(tampered)
        tampered = deepcopy(game)
        tampered["trace"][0]["digest"] = "0"*64
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(tampered)

    def test_incompatible_terrain_rules_and_fake_layout_digest_fail(self):
        scene = make_advanced_scene("parkour")
        forged = deepcopy(scene)
        forged["layout"]["obstacles"][0]["kind"] = "unlimited_teleport"
        with self.assertRaises(SceneError):
            validate_advanced_scene(forged)
        forged = deepcopy(scene)
        forged["layout"]["medals"][0]["x"] = scene["layout"]["medals"][1]["x"]
        with self.assertRaises(SceneError):
            make_advanced_scene("parkour", layout=forged["layout"])
        forged = deepcopy(scene)
        forged["digest"] = "f"*64
        with self.assertRaises(SceneError):
            validate_advanced_scene(forged)

    def test_bound_source_settings_are_not_unchecked_free_victories(self):
        for values in (
            {"max_stride": 8, "course_length": 36},
            {"sprint_cost": 30, "stamina": 10},
            {"grapple_reach": 0, "grapple_charges": 4},
            {"double_jump": 1},
            {"difficulty": "invulnerable"},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("parkour", values)
        with self.assertRaises(ParkourActionError):
            step(start(make_editor_document("parkour")["settings"], 0),
                 make_editor_document("parkour")["settings"], "double_jump")

if __name__ == "__main__":
    unittest.main()
