"""Original standalone sandbox: persistent ecology, typed source and audit proofs."""
from __future__ import annotations

from copy import deepcopy
import io
import json
import unittest
from contextlib import redirect_stdout

from skeleton.ai.game_builder.advanced_sandbox_runtime import (
    SIZE,CELLS,TERRAINS,BUILDINGS,JOBS,ACTIONS,COSTS,SandboxActionError,
    default_layout,generated_chunk,normalize_layout,start,step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,validate_advanced_scene,SceneError,
)
from skeleton.ai.game_builder.system_editors import (
    make_editor_document,catalog,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)


class OriginalEndlessSandboxTests(unittest.TestCase):
    def test_fifteenth_real_editor_65_controls_and_4096_seeded_chunks(self):
        self.assertIn("sandbox", ENGINES)
        self.assertEqual(set(ACTION_HELP["sandbox"]),set(ACTIONS))
        self.assertGreater(len(ACTIONS),1000)
        spec=next(s for s in catalog() if s["id"]=="sandbox")
        self.assertEqual(len(spec["fields"]),65)
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertEqual(len(generated_chunk(3,4095)),CELLS)
        self.assertNotEqual(generated_chunk(3,0),generated_chunk(3,4095))
        self.assertEqual(generated_chunk(3,4095),generated_chunk(3,4095))
        with self.assertRaises(SandboxActionError):
            generated_chunk(3,4096)

    def test_original_authored_64_cell_world_validates_across_seeds(self):
        for seed in (0,1,2,3,7,21,99,123456):
            rules=make_editor_document("sandbox")["settings"]
            source=default_layout(rules,seed)
            self.assertEqual(len(source["tiles"]),CELLS)
            self.assertEqual(source,normalize_layout(rules,source))
            self.assertEqual(source["spawn"],0)
            self.assertEqual(source["tiles"][1]["terrain"],"forest")
            self.assertEqual(source["tiles"][8]["terrain"],"ridge")
            self.assertEqual(sum(t["animal"] for t in source["tiles"]),
                             source["wildlife_population"])
            self.assertEqual(len(source["settler_spawns"]),2)
            scene=make_advanced_scene("sandbox",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            report=run_advanced_session("sandbox",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(report))
            self.assertEqual(report["state"]["region"],0)
            self.assertEqual(report["state"]["visited_regions"],[0])

    def test_world_tiles_and_deposits_are_finite_and_independently_replayed(self):
        settings={"creative_mode":False,"work_energy":0,
                  "move_energy":0,"carry_capacity":500}
        source=run_advanced_session("sandbox",settings,["chop:1","quarry:8"])
        self.assertTrue(verify_advanced_session(source,settings))
        cell1=source["state"]["regions"]["0"][1]
        cell8=source["state"]["regions"]["0"][8]
        initial=default_layout(make_editor_document("sandbox",settings)["settings"],0)
        self.assertLess(cell1["wood"],initial["tiles"][1]["wood"])
        self.assertLess(cell8["stone"],initial["tiles"][8]["stone"])
        self.assertGreater(source["state"]["inventory"]["wood"],10)
        self.assertGreater(source["state"]["inventory"]["stone"],8)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",settings,["chop:8"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",settings,["quarry:1"])
        cfg=make_editor_document("sandbox",settings)["settings"]
        s=start(cfg,0)
        for _ in range(10):
            if s["regions"]["0"][1]["wood"]==0:break
            step(s,cfg,"chop:1")
        self.assertEqual(s["regions"]["0"][1]["wood"],0)
        with self.assertRaises(SandboxActionError):
            step(s,cfg,"chop:1")

    def test_unlimited_policy_requires_matching_original_terrain(self):
        cfg={"creative_mode":False,"resource_policy":"unlimited",
             "work_energy":0,"carry_capacity":1000}
        s=run_advanced_session("sandbox",cfg,["chop:1"]*7)
        self.assertEqual(s["state"]["regions"]["0"][1]["wood"],
                         default_layout(make_editor_document("sandbox",cfg)["settings"],0)["tiles"][1]["wood"])
        self.assertEqual(s["state"]["inventory"]["wood"],31)
        for action in ("chop:8","quarry:1","fish:0","draw_water:0"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("sandbox",cfg,[action])

    def test_survival_construction_charges_actual_credits_stock_and_energy(self):
        cfg={"creative_mode":False}
        session=run_advanced_session("sandbox",cfg,["build:house:0"])
        self.assertTrue(verify_advanced_session(session,cfg))
        state=session["state"]
        self.assertEqual(state["regions"]["0"][0]["building"],"house")
        self.assertEqual(state["inventory"]["wood"],10-COSTS["house"]["wood"])
        self.assertEqual(state["inventory"]["stone"],8-COSTS["house"]["stone"])
        self.assertEqual(state["credits"],400-2)
        self.assertEqual(state["houses"],1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",cfg,["build:house:0","build:house:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",cfg,["build:bridge:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",cfg,["build:house:0","build:house:1"])

    def test_crop_soil_water_growth_and_yield_are_real(self):
        actions=["till:0","sow:0","irrigate:0","tick:4","reap:0"]
        state=run_advanced_session("sandbox",actions=actions)["state"]
        self.assertEqual(state["inventory"]["food"],10+4)
        self.assertEqual(state["inventory"]["seed"],7)
        self.assertEqual(state["regions"]["0"][0]["crop"],0)
        self.assertTrue(state["regions"]["0"][0]["soil"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["sow:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["till:0","sow:0","reap:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=actions+["reap:0"])

    def test_fishing_requires_aquatic_stock_and_can_be_exhausted(self):
        cfg=make_editor_document("sandbox",{"work_energy":0})["settings"]
        s=start(cfg,0)
        step(s,cfg,"move:1")
        fish=s["regions"]["0"][9]["fish"]
        self.assertGreaterEqual(fish,3)
        for _ in range(fish):
            step(s,cfg,"fish:9")
        self.assertEqual(s["regions"]["0"][9]["fish"],0)
        with self.assertRaises(SandboxActionError):
            step(s,cfg,"fish:9")
        self.assertGreater(s["inventory"]["food"],10)

    def test_persistent_streaming_revisits_do_not_reset_wood_or_crops(self):
        cfg={"world_regions":4096}
        commands=["chop:1","till:0","sow:0","region:next",
                  "chop:1","region:previous"]
        result=run_advanced_session("sandbox",cfg,commands,seed=12)
        self.assertTrue(verify_advanced_session(result,cfg))
        state=result["state"]
        self.assertEqual(state["region"],0)
        self.assertEqual(state["visited_regions"],[0,1])
        self.assertEqual(state["regions"]["0"][0]["crop"],1)
        self.assertLess(state["regions"]["0"][1]["wood"],
                        default_layout(make_editor_document("sandbox",cfg)["settings"],12)["tiles"][1]["wood"])
        self.assertLess(state["regions"]["1"][1]["wood"],
                        generated_chunk(12,1)[1]["wood"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",{"world_regions":1},["region:next"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["region:previous"])

    def test_settler_forester_actually_exhausts_nearby_source_and_not_other_chunk(self):
        cfg=make_editor_document("sandbox")["settings"]
        state=start(cfg,2)
        step(state,cfg,"move:1")
        step(state,cfg,"move:2")
        step(state,cfg,"assign:forester")
        before=state["regions"]["0"][1]["wood"]
        step(state,cfg,"tick")
        self.assertEqual(state["regions"]["0"][1]["wood"],before-1)
        self.assertEqual(state["settlers"][0]["job"],"forester")
        self.assertEqual(state["settlers"][0]["worked"],1)
        step(state,cfg,"region:next")
        other=state["regions"]["1"][1]["wood"]
        step(state,cfg,"tick")
        self.assertEqual(state["regions"]["1"][1]["wood"],other)
        self.assertEqual(state["settlers"][0]["worked"],1)
        with self.assertRaises(SandboxActionError):
            step(state,cfg,"assign:miner")

    def test_creative_is_nonterminal_by_default_but_can_author_real_win(self):
        never=run_advanced_session("sandbox",actions=["build:house:0","tick"])
        self.assertIn("self_sustaining_homestead",never["state"]["achievements"])
        self.assertFalse(never["terminal"])
        self.assertFalse(never["state"]["finished"])
        after=run_advanced_session("sandbox",actions=["build:house:0","tick",
                                                      "region:next"])
        self.assertTrue(verify_advanced_session(after))
        self.assertEqual(after["state"]["region"],1)
        ending={"allow_perpetual_play":False}
        done=run_advanced_session("sandbox",ending,["build:house:0","tick"])
        self.assertTrue(done["terminal"])
        self.assertTrue(done["state"]["finished"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",ending,["build:house:0","tick",
                                                   "region:next"])

    def test_fuel_consumption_and_generators_do_not_produce_free_energy(self):
        actions=["build:generator:0","tick:4","tick"]
        state=run_advanced_session("sandbox",actions=actions)["state"]
        self.assertEqual(state["inventory"]["fuel"],0)
        self.assertEqual(state["power"],4*5)
        self.assertEqual(state["emissions"],4)
        self.assertEqual(state["regions"]["0"][0]["building"],"generator")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["portal:next"])

    def test_fire_suppression_reduces_actual_terrain_damage(self):
        fire=run_advanced_session("sandbox",actions=["ignite:1","tick"])
        source=default_layout(make_editor_document("sandbox")["settings"],0)
        tile=fire["state"]["regions"]["0"][1]
        self.assertLess(tile["wood"],source["tiles"][1]["wood"])
        self.assertGreater(tile["pollution"],0)
        self.assertGreater(tile["fire"],0)
        controlled=run_advanced_session("sandbox",
                                        actions=["ignite:1","extinguish:1","tick"])
        self.assertEqual(controlled["state"]["regions"]["0"][1]["fire"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["extinguish:1"])

    def test_finite_market_disallows_unearned_ore_and_funds(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["trade:sell_ore"])
        sale=run_advanced_session("sandbox",actions=["mine_ore:8","trade:sell_ore"])
        self.assertGreater(sale["state"]["credits"],400)
        self.assertTrue(verify_advanced_session(sale))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",{"trading":False},
                                 actions=["trade:buy_food"])

    def test_hard_difficulty_exposure_and_rationing(self):
        cfg={"creative_mode":False,"hunger_gain":25,
             "thirst_gain":25,"hunger_threshold":20,
             "thirst_threshold":20,"exposure_damage":7,
             "starvation_damage":6}
        report=run_advanced_session("sandbox",cfg,["tick:4"])
        self.assertLess(report["state"]["health"],60)
        self.assertGreaterEqual(report["state"]["hunger"],20)
        self.assertEqual(report["state"]["ticks"],4)
        relaxed=run_advanced_session("sandbox",
           {**cfg,"creative_mode":True},["tick:4"])
        self.assertEqual(relaxed["state"]["health"],60)

    def test_authored_source_rejects_forged_map_and_inventory_creating_cells(self):
        scene=make_advanced_scene("sandbox",seed=5)
        baseline=scene["layout"]
        for change in (
            lambda x:x["tiles"][0].update(wood=True),
            lambda x:x["tiles"].append(deepcopy(x["tiles"][0])),
            lambda x:x["tiles"][8].update(building="pirated_binary"),
            lambda x:x["tiles"][8].update(resource_script="exec"),
            lambda x:x["tiles"][0].update(terrain="lake"),
            lambda x:x["tiles"][1].update(animal=2),
            lambda x:x.update(wildlife_population=500),
            lambda x:x.update(settler_spawns=[2,2]),
            lambda x:x["tiles"][1].update(id=3),
        ):
            altered=deepcopy(baseline)
            change(altered)
            with self.assertRaises(SandboxActionError):
                normalize_layout(make_editor_document("sandbox")["settings"],altered)
        altered=deepcopy(scene)
        altered["layout"]["tiles"][1]["wood"]+=1
        with self.assertRaises(SceneError):
            validate_advanced_scene(altered)
        with self.assertRaises(SceneError):
            validate_advanced_scene(scene,{"world_regions":22})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",seed=6,scene=scene)

    def test_forged_receipt_or_savegame_does_not_create_resources(self):
        cfg={"creative_mode":False,"work_energy":0}
        scene=make_advanced_scene("sandbox",cfg,seed=9)
        initial=run_advanced_session("sandbox",cfg,
                      ["chop:1","quarry:8"],seed=9,scene=scene)
        self.assertTrue(verify_advanced_session(initial,cfg))
        save=export_advanced_savegame(initial,cfg)
        self.assertEqual(import_advanced_savegame(save)["session"],initial)
        resumed=continue_advanced_savegame(save,["region:next"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for mutate in (
            lambda s:s["inventory"].update(wood=99999),
            lambda s:s["regions"]["0"][1].update(ore=99999),
            lambda s:s.update(finished=True),
            lambda s:s["regions"].update({"77":generated_chunk(3,77)}),
            lambda s:s["settlers"][0].update(skill=99),
        ):
            receipt=deepcopy(initial)
            mutate(receipt["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(receipt,cfg)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["tick"]*129)

    def test_actual_hybrid_assembly_includes_source_bound_endless_sandbox(self):
        cfg={"world_regions":18}
        source=make_advanced_scene("sandbox",cfg,seed=0)
        assembly=compile_system_assembly("original_persistent_play",
                    [make_editor_document("sandbox",cfg)],
                    authorized=True,scenes=[source])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["authored_scene_evidence"][0]["editor"],"sandbox")
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"sandbox")
        self.assertFalse(assembly["ready_for_release"])


    def test_studio_has_playable_persistent_map_and_supervised_terrain_tools(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            render_workspace_html,SCRIPT,
        )
        document=render_workspace_html("A"*32).decode("utf-8")
        for item in ("sandbox-target-cell","sandbox-registered-action",
                     "selectedSandboxCell","paintSandboxCell",
                     "Execute verified world operation","terrain_next",
                     "animal_toggle","tamed_toggle","structure_next",
                     "credits_plus","settler_toggle","sandbox"):
            self.assertIn(item,document)
        self.assertIn("Sandbox source changed. Validate geography",SCRIPT)
        self.assertIn("state.regions[String(state.region)]",SCRIPT)
        original=make_advanced_scene("sandbox",seed=7)
        modified=deepcopy(original)
        modified["layout"]["tiles"][1]["wood"]+=2
        with self.assertRaises(SceneError):
            validate_advanced_scene(modified)
        rebuilt=make_advanced_scene("sandbox",seed=7,layout=modified["layout"])
        self.assertNotEqual(original["digest"],rebuilt["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("sandbox",seed=7,scene=rebuilt)))

    def test_wells_and_kilns_have_real_utilities_and_power_budget(self):
        self.assertRaises(AdvancedRuntimeError,run_advanced_session,
                          "sandbox",None,["craft:brick"])
        self.assertRaises(AdvancedRuntimeError,run_advanced_session,
                          "sandbox",None,["craft:tool"])
        well=run_advanced_session("sandbox",actions=["build:well:1","tick"])
        s=well["state"]
        self.assertEqual(s["regions"]["0"][1]["building"],"well")
        self.assertGreater(s["community_water"],12-1)
        initial=default_layout(make_editor_document("sandbox")["settings"],0)
        self.assertLess(s["regions"]["0"][9]["water"],initial["tiles"][9]["water"])
        workshop=run_advanced_session("sandbox",
             {"creative_mode":False},["build:workshop:0","craft:tool"])
        self.assertEqual(workshop["state"]["inventory"]["tool"],3)
        self.assertEqual(workshop["state"]["inventory"]["ore"],0)

    def test_real_local_wildlife_and_regrowth_depend_on_policy(self):
        renewable={"resource_policy":"renewable","regrowth_period":1,
                   "regrowth_cap":50,"wildlife_birth_period":1,
                   "wildlife_move_period":1,"wildlife_cap":64}
        grown=run_advanced_session("sandbox",renewable,["chop:1","tick"])
        cfg=make_editor_document("sandbox",renewable)["settings"]
        start_source=default_layout(cfg,0)
        tile=grown["state"]["regions"]["0"][1]
        initial=start_source["tiles"][1]["wood"]
        chopped=min(cfg["harvest_strength"],initial)
        self.assertEqual(tile["wood"],initial-chopped+1)
        self.assertGreaterEqual(sum(t["animal"] for t in grown["state"]["regions"]["0"]),
                                start_source["wildlife_population"])
        finite=run_advanced_session("sandbox",
                 {"resource_policy":"finite","regrowth_period":1},
                 ["chop:1","tick"])
        self.assertEqual(finite["state"]["regions"]["0"][1]["wood"],
                         initial-chopped)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",{"wildlife_move_period":0})

    def test_terrain_rewrites_reject_built_tiles_and_noncreative_cheating(self):
        moved=run_advanced_session("sandbox",actions=["terraform:lake:0"])
        self.assertEqual(moved["state"]["regions"]["0"][0]["terrain"],"lake")
        self.assertEqual(moved["state"]["regions"]["0"][0]["water"]>0,True)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",{"creative_mode":False},
                                 ["terraform:lake:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["build:house:0","terraform:lake:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sandbox",actions=["till:0","sow:0","terraform:lake:0"])

    def test_reference_cli_is_offline_non_native_and_no_malicious_action(self):
        from skeleton.ai.game_builder.system_editor_cli import main
        out=io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["play","--editor","sandbox","--seed","5"]),0)
        receipt=json.loads(out.getvalue())
        self.assertTrue(verify_advanced_session(receipt))
        self.assertFalse(receipt["native_hardware_verified"])
        self.assertFalse(receipt["publication_certified"])
        for bad in ("exec:python","set_inventory:100000","teleport:63",
                    "hack:savegame","build:copyright_asset:1"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("sandbox",actions=[bad])


if __name__=="__main__":
    unittest.main()
