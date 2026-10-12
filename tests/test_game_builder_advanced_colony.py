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
        self.assertEqual(result["session"]["editor"], "colony")
        next_save = continue_advanced_savegame(save, ["build:well", "tick"])
        self.assertTrue(verify_advanced_session(import_advanced_savegame(next_save)["session"], cfg))

    def test_original_population_and_water_depletion_are_real(self):
        cfg = {"settlers": 1, "jobs": 1, "threats": "off", "need_decay": 20}
        scene = make_advanced_scene("colony", cfg, seed=0)
        result = run_advanced_session("colony", cfg, ["tick:4"] * 2,
                                      scene=scene)
        self.assertTrue(result["state"]["failed"])
        self.assertTrue(result["terminal"])
        self.assertEqual(result["state"]["population"], 0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", cfg, ["tick:4"] * 2 + ["rest"], scene=scene)

    def test_game_actions_not_arbitrary_code(self):
        for cmd in ("eval('1')", "teleport:all", "mine:50000", "trade:infinite"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("colony", actions=[cmd])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("colony", actions=["tick"] * 129)



class OriginalColonyNativeSourceTests(unittest.TestCase):
    def test_native_game_independently_implements_complete_state(self):
        from skeleton.ai.game_builder.advanced_colony_godot import (
            render_colony_godot_package, SCHEMA, PROOF_SCHEMA,
            PROOF_FIELDS, GODOT_COLONY,
        )
        from skeleton.ai.game_builder.advanced_godot_export import (
            archive_advanced_godot_package, AdvancedGodotExportError,
        )
        from hashlib import sha256
        config = {"worker_productivity": 2, "raid_interval": 4,
                  "disasters": "frequent", "ending_policy": "endless"}
        actions = ["build:farm", "assign:farmers", "assign:guards",
                   "fortify", "forage", "tick:4", "scavenge", "tick"]
        scene = make_advanced_scene("colony", config, seed=8)
        game = run_advanced_session("colony", config, actions, seed=8, scene=scene)
        native = render_colony_godot_package(game, config, authorized=True)
        self.assertEqual(native.manifest["native_editor"], "colony")
        self.assertEqual(native.manifest["native_adapter"], "godot4_independent_colony")
        self.assertFalse(native.manifest["godot_executed"])
        self.assertFalse(native.manifest["publish_approved"])
        manifest = native.manifest["files"]
        self.assertEqual(manifest["godot/scripts/main.gd"],
                         sha256(native.files["godot/scripts/main.gd"]).hexdigest())
        proof = json.loads(native.files["godot/proof.json"])
        authored = json.loads(native.files["godot/game.json"])
        self.assertEqual(proof["schema"], PROOF_SCHEMA)
        self.assertEqual(authored["schema"], SCHEMA)
        self.assertEqual(proof["expected"], game["state"])
        self.assertEqual(len(PROOF_FIELDS), len(game["state"]))
        self.assertEqual(proof["actions"], actions)
        self.assertIn("func _advance()", GODOT_COLONY)
        self.assertIn("func _verify()", GODOT_COLONY)
        self.assertIn("colony_raid_breached_defenses", GODOT_COLONY)
        self.assertEqual(native.files, render_colony_godot_package(
            game, config, authorized=True).files)
        self.assertEqual(archive_advanced_godot_package(native),
                         archive_advanced_godot_package(
                             render_colony_godot_package(game, config, authorized=True)))
        with self.assertRaises(PermissionError):
            render_colony_godot_package(game, config, authorized=False)
        forged = deepcopy(game)
        forged["state"]["water"] += 200
        with self.assertRaises(AdvancedRuntimeError):
            render_colony_godot_package(forged, config, authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_colony_godot_package(
                run_advanced_session("farming"), authorized=True)

    def test_all_fifteen_editor_axes_are_applied_by_game(self):
        from skeleton.ai.game_builder.advanced_colony_godot import PROOF_FIELDS
        base = make_editor_document("colony")["settings"]
        self.assertEqual(len(base), 15)
        self.assertTrue({"starting_credits", "initial_stores", "worker_productivity",
                         "water_yield", "raid_interval", "disease_pressure",
                         "food_policy", "disasters", "ending_policy",
                         "allow_migration"} <= set(base))
        run = lambda cfg, actions: run_advanced_session(
            "colony", cfg, actions=actions)["state"]
        self.assertEqual(run({"starting_credits": 44}, [])["credits"], 44)
        self.assertEqual(run({"initial_stores": 55}, [])["food"], 55)
        self.assertGreater(run({"worker_productivity": 4},
                              ["build:farm", "assign:farmers", "tick"])["food"],
                           run({"worker_productivity": 1},
                              ["build:farm", "assign:farmers", "tick"])["food"])
        self.assertGreater(run({"water_yield": 7},
                              ["build:well", "tick"])["water"],
                           run({"water_yield": 1},
                              ["build:well", "tick"])["water"])
        self.assertEqual(run({"threats": "scheduled", "raid_interval": 3},
                             ["tick"])["injured"], 0)
        self.assertGreater(run({"threats": "scheduled", "raid_interval": 3},
                               ["tick"]*2)["injured"], 0)
        self.assertEqual(run({"disease_pressure": 0, "threats": "off",
                              "disasters": "off"}, ["tick"]*6)["injured"], 0)
        self.assertGreater(run({"disease_pressure": 6, "threats": "off",
                                "disasters": "off"}, ["tick"]*6)["injured"], 0)
        self.assertGreater(run({"food_policy": "frugal"}, ["tick"])["food"],
                           run({"food_policy": "abundant"}, ["tick"])["food"])
        with self.assertRaises(AdvancedRuntimeError):
            run({"allow_migration": False}, ["recruit"])
        self.assertEqual(set(PROOF_FIELDS), set(run({}, [])))

    def test_forged_native_document_does_not_grant_write_or_certification(self):
        from skeleton.ai.game_builder.advanced_colony_godot import (
            render_colony_godot_package,
        )
        native = render_colony_godot_package(
            run_advanced_session("colony", actions=["tick"]), authorized=True)
        self.assertFalse(native.manifest["native_hardware_certified"])
        self.assertFalse(native.manifest["publish_approved"])
        self.assertIn(b"--verify-colony", native.files["godot/scripts/main.gd"])
        self.assertIn(b"playable", native.files["godot/scripts/main.gd"])


if __name__ == "__main__":
    unittest.main()
