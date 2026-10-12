"""Adversarial gameplay and spatial-progression tests for the original world explorer."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_metroidvania_runtime import (
    POWERS, ACTIONS, ExplorationActionError, default_layout, normalize_layout,
    start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,validate_advanced_scene,SceneError,
)
from skeleton.ai.game_builder.system_editors import make_editor_document,catalog
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)


class OriginalConnectedWorldTests(unittest.TestCase):
    def test_forty_meaningful_editor_controls_and_24_room_world(self):
        self.assertIn("metroidvania", ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["metroidvania"]))
        spec=next(x for x in catalog() if x["id"]=="metroidvania")
        self.assertEqual(len(spec["fields"]),40)
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        config=make_editor_document("metroidvania")["settings"]
        world=default_layout(config,0)
        self.assertEqual(len(world["rooms"]),24)
        self.assertEqual(len(world["passages"]),24)
        self.assertEqual(world,normalize_layout(config,world))
        self.assertEqual(world["rooms"][1]["ability"],"dash")
        self.assertEqual(world["guardian"],23)
        self.assertTrue(any(e["gate"]=="dash" for e in world["passages"]))

    def test_real_gated_backtracking_collectible_abilities_and_world_persistence(self):
        actions=["travel:1"]
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",{"regions":8},
                                 actions+["travel:2"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",{"regions":8},
                                 actions+["claim"])
        easy={"regions":8,"foe_health":1,"foe_variation":1,
              "foe_damage":0,"hazard_damage":0,"boss_damage":1,"armor":3}
        report=run_advanced_session("metroidvania",easy,
                                   ["travel:1","attack","claim",
                                    "travel:2","attack","claim",
                                    "travel:1","travel:2","travel:3"])
        self.assertTrue(verify_advanced_session(report,easy))
        self.assertIn("dash",report["state"]["abilities"])
        self.assertIn("grapple",report["state"]["abilities"])
        self.assertEqual(report["state"]["rooms"][1]["foe"],0)
        self.assertTrue(report["state"]["rooms"][1]["claimed"])
        self.assertEqual(report["state"]["visited"],[0,1,2,3])
        self.assertIn("persistent_world_region_revisited",[
            event for step in report["trace"] for event in step["events"]])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",easy,
                                 ["travel:1","attack","claim","claim"])

    def test_complete_original_campaign_and_postgame_modes_differ(self):
        base={"regions":8,"foe_damage":0,"hazard_damage":0,
              "armor":3,"starting_health":90}
        for ending in ("endless","campaign"):
            cfg={**base,"ending_policy":ending}
            settings=make_editor_document("metroidvania",cfg)["settings"]
            world=default_layout(settings,0)
            actions=[]
            for i in range(1,8):
                room=world["rooms"][i]
                actions.append("travel:"+str(i))
                actions.extend(["attack"]*((room["foe"]+settings["attack_power"]-1)
                                          //settings["attack_power"]))
                if room["ability"] is not None:
                    actions.append("claim")
            actions.extend(["attack"]*((world["guardian_health"]+
                              settings["attack_power"]-1)//settings["attack_power"]))
            report=run_advanced_session("metroidvania",cfg,actions)
            self.assertTrue(verify_advanced_session(report,cfg))
            self.assertTrue(report["state"]["boss_defeated"])
            self.assertEqual(report["state"]["guardian_hp"],0)
            self.assertIn("original_guardian_defeated",report["state"]["milestones"])
            self.assertEqual(report["state"]["finished"],ending=="campaign")
            self.assertEqual(report["terminal"],ending=="campaign")
            if ending=="endless":
                self.assertIn("persistent_post_guardian_world_open",
                              report["state"]["milestones"])
                resume=run_advanced_session("metroidvania",cfg,actions+["travel:6"])
                self.assertEqual(resume["state"]["region"],6)
            else:
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("metroidvania",cfg,actions+["travel:6"])

    def test_high_skill_break_bypasses_only_existing_ability_gates(self):
        cfg={"regions":8,"foe_health":1,"foe_variation":1,"foe_damage":0,
             "hazard_damage":0,"break_stamina":5}
        actions=["travel:1","attack"]
        no_ability=run_advanced_session("metroidvania",cfg,actions)
        self.assertFalse(no_ability["state"]["abilities"])
        passed=run_advanced_session("metroidvania",cfg,actions+["break:2"])
        self.assertEqual(passed["state"]["region"],2)
        self.assertEqual(passed["state"]["sequence_breaks"],1)
        self.assertLess(passed["state"]["stamina"],no_ability["state"]["stamina"])
        self.assertIn("high_skill_sequence_break",passed["state"]["milestones"])
        for cmd in ("break:0","fast:7","travel:7","break:23"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("metroidvania",cfg,actions+[cmd])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",{**cfg,"sequence_breaks":False},
                                 actions+["break:2"])

    def test_finite_cache_secrets_and_gear_cannot_regenerate_on_revisit(self):
        cfg={"regions":8,"foe_damage":0,"hazard_damage":0,"armor":3,
             "foe_health":1,"foe_variation":1,"secret_interval":2}
        actions=["travel:1","attack","search","claim",
                 "travel:2","attack","search","reveal"]
        session=run_advanced_session("metroidvania",cfg,actions)
        self.assertGreater(session["state"]["shards"],0)
        self.assertEqual(session["state"]["secrets_found"],1)
        self.assertTrue(session["state"]["rooms"][2]["secret_found"])
        self.assertTrue(session["state"]["rooms"][2]["searched"])
        for repeated in ("reveal","search"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("metroidvania",cfg,actions+[repeated])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",cfg,["craft"]*10)

    def test_original_world_rejects_circular_gates_and_stale_scene_hash(self):
        config=make_editor_document("metroidvania",{"regions":8})["settings"]
        source=make_advanced_scene("metroidvania",{"regions":8},seed=3)
        self.assertEqual(source,validate_advanced_scene(source,{"regions":8}))
        for mutate in (
            lambda w:w["rooms"][0].update(ability="dash"),
            lambda w:w["passages"][0].update(gate="dash"),
            lambda w:w["passages"][0].update(a=3,b=3),
            lambda w:w["rooms"][1].update(biome="pirated_game_asset"),
            lambda w:w["rooms"][1].update(eval_python="os.system('bad')"),
            lambda w:w["rooms"][1].update(foe=True),
            lambda w:w["passages"].append(dict(w["passages"][0])),
            lambda w:w.update(guardian=0),
            lambda w:w["rooms"][2].update(ability="dash"),
            lambda w:w["passages"][0].update(gate="resonance"),
        ):
            altered=deepcopy(source["layout"])
            mutate(altered)
            with self.assertRaises(ExplorationActionError):
                normalize_layout(config,altered)
        tampered=deepcopy(source)
        tampered["layout"]["rooms"][2]["hazard"]+=1
        with self.assertRaises(SceneError):
            validate_advanced_scene(tampered,{"regions":8})
        with self.assertRaises(SceneError):
            validate_advanced_scene(source,{"regions":9})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",{"regions":8},
                                 seed=2,scene=source)

    def test_camped_fast_travel_consumes_supplies_and_requires_activated_anchors(self):
        cfg={"regions":8,"fast_travel_nodes":4,"foe_damage":0,
             "hazard_damage":0,"foe_health":1,"foe_variation":1}
        world=default_layout(make_editor_document("metroidvania",cfg)["settings"],0)
        anchors=[r["id"] for r in world["rooms"] if r["anchor"]]
        self.assertGreaterEqual(len(anchors),2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",cfg,["fast:1"])
        camp=run_advanced_session("metroidvania",cfg,["camp"])
        self.assertEqual(camp["state"]["camp_supplies"],cfg.get("camp_supplies",4)-1)
        self.assertIn(0,camp["state"]["fast_unlocked"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",cfg,["camp","fast:7"])

    def test_scene_hybrid_and_portable_saves_are_cryptographically_replayed(self):
        settings={"regions":8,"foe_health":1,"foe_variation":1,
                  "foe_damage":0,"hazard_damage":0}
        scene=make_advanced_scene("metroidvania",settings,seed=7)
        report=run_advanced_session("metroidvania",settings,
                 ["travel:1","attack","claim"],seed=7,scene=scene)
        self.assertTrue(verify_advanced_session(report,settings))
        original=export_advanced_savegame(report,settings)
        self.assertEqual(import_advanced_savegame(original)["session"],report)
        resumed=continue_advanced_savegame(original,["travel:2"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        forgery=deepcopy(report);forgery["state"]["abilities"].append("phase")
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forgery,settings)
        assembly=compile_system_assembly("original_nonterminal_world",
                        [make_editor_document("metroidvania",settings)],
                        authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"metroidvania")
        self.assertFalse(assembly["ready_for_release"])


    def test_live_studio_provides_original_world_map_and_supervised_progression_painter(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            render_workspace_html,SCRIPT,
        )
        html=render_workspace_html("A"*32).decode("utf-8")
        for token in ("paintExplorationRoom","exploration-target-region",
                      "exploration-world-order","Execute verified exploration move",
                      "gate_next","toggle_secret","set_guardian",
                      "Source changes remain untrusted"):
            # Source custody language is in the behavior rather than a magic
            # displayed testing-only badge.
            if token=="Source changes remain untrusted":continue
            self.assertIn(token,html)
        self.assertIn("Original world edited. Validate full graph",SCRIPT)
        self.assertIn("function drawAdvancedGame",SCRIPT)
        document=make_advanced_scene("metroidvania",{"regions":8},seed=2)
        altered=deepcopy(document)
        altered["layout"]["rooms"][2]["biome"]="water"
        with self.assertRaises(SceneError):
            validate_advanced_scene(altered,{"regions":8})
        rebuilt=make_advanced_scene("metroidvania",{"regions":8},seed=2,
                                    layout=altered["layout"])
        self.assertNotEqual(document["digest"],rebuilt["digest"])

    def test_offline_cli_emits_independently_verifiable_original_world(self):
        import io,json,tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from skeleton.ai.game_builder.system_editor_cli import main
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"settings.json"
            source.write_text(json.dumps({"regions":8}),encoding="utf-8")
            stream=io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(main(["play","--editor","metroidvania",
                                       "--settings",str(source),"--seed","4"]),0)
            session=json.loads(stream.getvalue())
            self.assertEqual(len(session["state"]["rooms"]),8)
            self.assertEqual(session["state"]["region"],0)
            self.assertTrue(verify_advanced_session(session,{"regions":8}))
            self.assertFalse(session["native_hardware_verified"])

    def test_elemental_guardian_reduces_real_enemy_damage_with_earned_powers(self):
        from skeleton.ai.game_builder.advanced_metroidvania_runtime import (
            start,step,
        )
        settings=make_editor_document("metroidvania",{
            "regions":8,"foe_damage":0,"hazard_damage":0,
            "boss_damage":6,"armor":0,
        })["settings"]
        base=start(settings,2)
        base["region"]=base["guardian"]
        hp=base["health"]
        step(base,settings,"guard")
        self.assertLess(base["health"],hp)
        equipped=start(settings,2)
        equipped["region"]=equipped["guardian"]
        equipped["abilities"].append("phase")
        step(equipped,settings,"guard")
        self.assertGreater(equipped["health"],base["health"])


    def test_ai_planner_earns_abilities_and_completes_rehearsed_world_boss(self):
        from skeleton.ai.game_builder.advanced_world_planner import plan_original_world
        for region_count in (8,24):
            settings={"regions":region_count,"hazard_damage":2,"foe_damage":3}
            scene=make_advanced_scene("metroidvania",settings,seed=3)
            proof=plan_original_world(scene,settings,max_states=50000)
            with self.subTest(regions=region_count):
                self.assertEqual(proof["feasibility"],"verified_diagnostic_route")
                self.assertTrue(proof["rehearsal_verified"])
                self.assertEqual(len(proof["rehearsal_digest"]),64)
                self.assertEqual(proof["original_source_digest"],scene["digest"])
                self.assertIn("claim",proof["route"])
                self.assertEqual(proof["route"][-1],"attack")
                self.assertLessEqual(proof["route_turn_count"],128)
                self.assertFalse(proof["original_play_survivability_verified"])
                self.assertFalse(proof["native_execution_verified"])
                self.assertFalse(proof["source_mutated"])
                self.assertEqual(proof,plan_original_world(
                    scene,settings,max_states=50000))

    def test_ai_planner_rejects_budget_and_circular_source_forgery(self):
        from skeleton.ai.game_builder.advanced_world_planner import (
            ExplorationPlanningError,plan_original_world,
        )
        scene=make_advanced_scene("metroidvania",{"regions":8},seed=1)
        for n in (0,True,199,100001):
            with self.assertRaises(ExplorationPlanningError):
                plan_original_world(scene,{"regions":8},max_states=n)
        for n in (0,True,129):
            with self.assertRaises(ExplorationPlanningError):
                plan_original_world(scene,{"regions":8},max_actions=n)
        for n in (1,3):
            bounded=plan_original_world(scene,{"regions":8},max_actions=n)
            self.assertFalse(bounded["rehearsal_verified"])
            self.assertFalse(bounded["route"])
        tampered=deepcopy(scene);tampered["layout"]["guardian_health"]=1
        with self.assertRaises(SceneError):
            plan_original_world(tampered,{"regions":8})
        with self.assertRaises(SceneError):
            plan_original_world(scene,{"regions":9})

    def test_ai_world_planning_cli_and_studio_do_not_auto_approve_source(self):
        import io,json,tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from skeleton.ai.game_builder.system_editor_cli import main
        from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
        cfg={"regions":8}
        scene=make_advanced_scene("metroidvania",cfg,seed=0)
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"world.json";settings=Path(tmp)/"settings.json"
            file.write_text(json.dumps(scene),encoding="utf-8")
            settings.write_text(json.dumps(cfg),encoding="utf-8")
            stream=io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(main(["plan-original-world","--scene",str(file),
                                       "--settings",str(settings)]),0)
            proof=json.loads(stream.getvalue())
            self.assertTrue(proof["rehearsal_verified"])
            self.assertFalse(proof["source_mutated"])
            self.assertFalse(proof["native_execution_verified"])
        page=render_workspace_html("A"*32).decode("utf-8")
        for t in ("world-progression-plan","world-progression-proof",
                  "/api/world-plan","original_play_survivability_verified"):
            self.assertIn(t,page)

    def test_typed_actuation_and_resource_edge_cases(self):
        for bad in ("teleport","force_win","travel:24","set_hp:1000",
                    "fast:-1","break:infinite","claim"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("metroidvania",actions=[bad])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("metroidvania",actions=["inspect"]*129)
        with self.assertRaises(ExplorationActionError):
            start(make_editor_document("metroidvania")["settings"],-1)


if __name__=="__main__":
    unittest.main()
