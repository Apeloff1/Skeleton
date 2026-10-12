"""Real colony gameplay contracts: finite economy, authored geography, replay and custody."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.advanced_colony_runtime import (
    ACTIONS, BUILDINGS, ROLES, ColonyActionError, default_layout,
    normalize_layout, start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import catalog, make_editor_document
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)


class OriginalColonyRuntimeTests(unittest.TestCase):
    def test_advanced_editor_and_actual_playable_rules(self):
        self.assertIn("colony", ENGINES)
        self.assertGreaterEqual(len(ACTIONS), 32)
        self.assertEqual(len(ROLES), 6)
        self.assertEqual(len(BUILDINGS), 6)
        family = next(c for c in catalog() if c["id"] == "colony")
        self.assertEqual(family["runtime_maturity"], "advanced_reference_runtime")
        self.assertEqual(family["progression_floor"], "advanced")
        self.assertEqual(make_editor_document("colony")["settings"]["settlers"], 12)

    def test_real_job_scheduling_farming_water_and_nonaligned_state(self):
        actions = ["build:farm", "build:well", "assign:farmers",
                   "assign:farmers", "assign:farmers", "assign:gatherers",
                   "assign:miners", "tick:4", "expedition", "tick:4"]
        authored = make_advanced_scene("colony", seed=4)
        result = run_advanced_session("colony", actions=actions, seed=4, scene=authored)
        self.assertTrue(verify_advanced_session(result))
        self.assertEqual(result["state"]["day"], 9)
        self.assertEqual(result["state"]["workers"]["farmers"], 3)
        self.assertEqual(result["state"]["buildings"]["well"], 1)
        self.assertIn("self_sufficient_settlement", result["state"]["milestones"])
        self.assertFalse(result["terminal"])  # legitimate endless play
        self.assertGreater(result["state"]["expeditions"], 0)
        self.assertGreater(result["state"]["food"], 0)
        self.assertTrue(any("assigned_labor_produced_finite_goods" in t["events"]
                            for t in result["trace"]))

    def test_crisis_requires_real_defense_and_threats_can_be_disabled(self):
        base = run_advanced_session("colony", actions=["tick:4"], seed=0)
        self.assertGreater(base["state"]["injured"], 0)
        self.assertIn("colony_raid_breached_defenses", base["state"]["events"])
        no_raid = run_advanced_session("colony", {"threats": "off"},
                                       actions=["tick:4"], seed=0)
        self.assertEqual(no_raid["state"]["injured"], 0)
        self.assertEqual(no_raid["state"]["threats_survived"], 0)
        guarded = run_advanced_session(
            "colony", actions=["assign:guards"] * 3 + ["tick:4"], seed=0)
        self.assertEqual(guarded["state"]["injured"], 0)
        self.assertEqual(guarded["state"]["threats_survived"], 1)

    def test_finite_stocks_are_not_fabricated_or_overdrawn(self):
        cfg = {"settlers": 6, "jobs": 5}
        layout = default_layout(make_editor_document("colony", cfg)["settings"], 0)
        layout["districts"][0]["wood"] = 1
        scene = make_advanced_scene("colony", cfg, layout=layout)
        state = run_advanced_session("colony", cfg,
                                    ["gather_wood"], scene=scene)["state"]
        self.assertEqual(state["wood"], 15)
        self.assertEqual(state["districts"][0]["wood"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg,
                                 ["gather_wood", "gather_wood"], scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg, ["assign:miners"] * 6, scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg, ["build:workshop", "build:clinic"], scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg, ["treat"], scene=scene)

    def test_sealed_scenes_violations_and_config_identity(self):
        settings = {"settlers": 8, "need_decay": 4}
        original = make_advanced_scene("colony", settings, seed=8)
        self.assertEqual(validate_advanced_scene(original, settings), original)
        for corrupt in (
            lambda p: p["layout"]["districts"][0].update(id=1),
            lambda p: p["layout"]["districts"][0].update(wood=-1),
            lambda p: p["layout"]["districts"][0].update(biome="copyrighted_map"),
            lambda p: p["layout"]["districts"].append(deepcopy(p["layout"]["districts"][0])),
            lambda p: p["layout"].update(injected_script="exec(...)"),
            lambda p: p.update(seed=9),
            lambda p: p.update(digest="0" * 64),
        ):
            candidate = deepcopy(original)
            corrupt(candidate)
            with self.assertRaises((SceneError, ColonyActionError)):
                validate_advanced_scene(candidate, settings)
        with self.assertRaises(SceneError):
            validate_advanced_scene(original, {"settlers": 7})

    def test_receipt_forgery_and_replay_save_continuation(self):
        cfg = {"need_decay": 1}
        session = run_advanced_session("colony", cfg,
                         ["build:farm", "assign:farmers", "tick"], seed=3)
        self.assertTrue(verify_advanced_session(session, cfg))
        for key, value in (("credits", 20000), ("population", 9999),
                           ("finished", True), ("food", 5000)):
            forged = deepcopy(session)
            forged["state"][key] = value
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged, cfg)
        save = export_advanced_savegame(session, cfg)
        result = import_advanced_savegame(save)
        self.assertEqual(result["editor"], "colony")
        next_save = continue_advanced_savegame(save, ["build:well", "tick"])
        self.assertTrue(verify_advanced_session(next_save["session"], cfg))

    def test_original_population_and_water_depletion_are_real(self):
        cfg = {"settlers": 1, "jobs": 1, "threats": "off", "need_decay": 20}
        scene = make_advanced_scene("colony", cfg, seed=0)
        result = run_advanced_session("colony", cfg, ["tick:4"] * 3,
                                      scene=scene)
        self.assertTrue(result["state"]["failed"])
        self.assertTrue(result["terminal"])
        self.assertEqual(result["state"]["population"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg, ["tick:4"] * 3 + ["rest"], scene=scene)

    def test_game_actions_not_arbitrary_code(self):
        for cmd in ("eval('1')", "teleport:all", "mine:50000", "trade:infinite"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("colony", actions=[cmd])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", actions=["tick"] * 129)


if __name__ == "__main__":
    unittest.main()
