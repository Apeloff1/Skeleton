"""Original roguelike reference: procedural floors, boss, permadeath and custody."""
from __future__ import annotations

from copy import deepcopy
import io
import json
import unittest
from contextlib import redirect_stdout

from skeleton.ai.game_builder.advanced_roguelike_runtime import (
    WIDTH,CELLS,BOONS,ACTIONS,RoguelikeActionError,
    default_layout,normalize_layout,start,step,
)
from skeleton.ai.game_builder.system_editors import (
    make_editor_document,catalog,SystemEditorError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)


class OriginalRoguelikeRunTests(unittest.TestCase):
    @staticmethod
    def easy(**overrides):
        return {
            "floors":2,"encounters_per_floor":1,
            "foe_health":1,"foe_health_growth":0,"health_variance":1,
            "foe_attack":0,"boss_health":1,"boss_health_growth":0,
            "boss_attack":1,"boss_armor":0,"enemy_patrol":False,
            "trap_damage":0,"starting_health":100,"attack_power":14,
            **overrides,
        }

    @staticmethod
    def route():
        # Actual spatial routes: obtain physical key from elite, traverse
        # outer perimeter avoiding signed inner walls; face real final boss.
        per_floor=(["move_east"]*4+["strike_east","move_east"]+
                   ["move_south"]*5)
        return per_floor+["take_stairs"]+per_floor+["strike_west","take_stairs"]

    def test_sixteenth_editor_has_77_typed_decision_controls(self):
        self.assertIn("roguelike",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["roguelike"]))
        spec=next(e for e in catalog() if e["id"]=="roguelike")
        self.assertEqual(len(spec["fields"]),77)
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertGreater(len(ACTIONS),25)

    def test_original_floor_maps_validated_for_many_seeds(self):
        for seed in (0,1,2,3,7,11,42):
            cfg=make_editor_document("roguelike")["settings"]
            layout=default_layout(cfg,seed)
            self.assertEqual(len(layout["terrain"]),CELLS)
            self.assertEqual(layout,normalize_layout(cfg,layout))
            self.assertEqual(layout["entry"],0)
            self.assertEqual(layout["exit"],35)
            self.assertTrue(layout["enemies"])
            scene=make_advanced_scene("roguelike",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            report=run_advanced_session("roguelike",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(report))
            self.assertEqual(report["state"]["player"],0)
            self.assertEqual(report["state"]["floor"],1)

    def test_real_two_floor_campaign_victory_through_actual_combat_and_exit(self):
        settings=self.easy()
        actions=self.route()
        report=run_advanced_session("roguelike",settings,actions)
        self.assertTrue(verify_advanced_session(report,settings))
        state=report["state"]
        self.assertTrue(report["terminal"])
        self.assertTrue(state["victory"])
        self.assertTrue(state["finished"])
        self.assertFalse(state["failed"])
        self.assertEqual(state["floor"],2)
        self.assertEqual(state["player"],35)
        self.assertTrue(state["floor_boss_defeated"])
        self.assertGreaterEqual(state["total_kills"],3)
        self.assertIn("original_procedural_dungeon_conquered",state["milestones"])
        self.assertEqual(sum("deterministic_original_next_floor_instantiated"
                             in step["events"] for step in report["trace"]),1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",settings,actions+["inspect"])

    def test_real_key_and_final_boss_cannot_be_bypassed(self):
        cfg=self.easy()
        for action in ("take_stairs","use_lockpick","loot_key","strike_east",
                       "shoot_east","open_chest","use_shrine","buy_potion"):
            with self.subTest(action=action):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("roguelike",cfg,[action])
        journey=["move_south"]*5+["move_east"]*5
        # Without defeating elite, lockpick opens exit on a genuine physical
        # tile, but cannot stand in for final guardian victory.
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",cfg,journey+["take_stairs"])
        first=run_advanced_session("roguelike",cfg,
                       journey+["use_lockpick","take_stairs"])
        self.assertEqual(first["state"]["floor"],2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",
                 self.easy(floors=1),journey+["use_lockpick","take_stairs"])

    def test_chests_are_single_use_and_stable_original_item_pool_variation(self):
        cfg=make_editor_document("roguelike",self.easy())["settings"]
        s=start(cfg,0)
        s["player"]=3 # testing engine transition directly, not claiming source replay
        chest=s["map"]["chests"][0]
        self.assertLessEqual(abs(chest%6-3)+abs(chest//6),4)
        s["player"]=chest
        relics=s["relics"]
        step(s,cfg,"open_chest")
        self.assertIn(chest,s["chests_opened"])
        self.assertEqual(s["relics"],relics+cfg["chest_relics"])
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"open_chest")
        a=run_advanced_session("roguelike",self.easy(item_pool=5))
        b=run_advanced_session("roguelike",self.easy(item_pool=2000))
        self.assertNotEqual(a["configuration_digest"],b["configuration_digest"])

    def test_directional_ray_attack_requires_actual_spatial_enemy(self):
        cfg=make_editor_document("roguelike",self.easy())["settings"]
        s=start(cfg,0)
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"strike_north")
        s["player"]=4
        enemy=next(e for e in s["map"]["enemies"] if e["cell"]==5)
        before=enemy["hp"]
        step(s,cfg,"strike_east")
        self.assertLess(enemy["hp"],before)
        self.assertEqual(enemy["hp"],0)
        self.assertTrue(state_has_key:=s["floor_key"])
        self.assertEqual(state_has_key,True)
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"strike_east")

    def test_real_spells_consume_mana_apply_stun_and_poison(self):
        cfg=make_editor_document("roguelike",{
            **self.easy(),"foe_health":20,"starting_mana":10,
            "spell_damage":2,"spell_poison":3,"spell_stun":2,
        })["settings"]
        s=start(cfg,0);s["player"]=4
        e=next(e for e in s["map"]["enemies"] if e["cell"]==5)
        before=s["mana"]
        step(s,cfg,"cast_east")
        self.assertEqual(s["mana"],before-cfg["spell_cost"])
        self.assertGreater(e["poison"],0)
        self.assertGreater(e["stun"],0)
        self.assertLess(e["hp"],e["max_hp"])
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"cast_north")

    def test_real_finite_shop_requires_proximity_money_and_original_supplies(self):
        cfg=make_editor_document("roguelike",self.easy())["settings"]
        s=start(cfg,0)
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"buy_potion")
        s["player"]=s["map"]["shop"]
        coins=s["gold"];potions=s["potions"]
        step(s,cfg,"buy_potion")
        self.assertEqual(s["gold"],coins-cfg["potion_price"])
        self.assertEqual(s["potions"],potions+1)
        with self.assertRaises(RoguelikeActionError):
            step(s,cfg,"upgrade_weapon")
        self.assertEqual(s["attack"],cfg["attack_power"])

    def test_paid_revival_differs_from_authoritative_permadeath(self):
        base=self.easy(foe_attack=12,armor=0,starting_health=5)
        for death in (True,False):
            cfg=make_editor_document("roguelike",
                  {**base,"permadeath":death,"revive_relic_cost":1})["settings"]
            s=start(cfg,0)
            s["player"]=4
            s["relics"]=1
            # Force actual nearby enemy contact by waiting; no arbitrary HP mutation.
            step(s,cfg,"inspect")
            self.assertEqual(s["failed"],death)
            if not death:
                self.assertGreater(s["hp"],0)
                self.assertEqual(s["relics"],0)
                self.assertEqual(s["player"],0)

    def test_actual_meta_policy_changes_rewards_not_just_description(self):
        for mode in ("none","unlocks","upgrades"):
            cfg=make_editor_document("roguelike",self.easy(meta_progress=mode))["settings"]
            s=start(cfg,0)
            s["relics"]=1
            if mode=="none":
                with self.assertRaises(RoguelikeActionError):
                    step(s,cfg,"bank_relic")
                continue
            before_attack=s["attack"];before_potion=s["potions"]
            step(s,cfg,"bank_relic")
            self.assertEqual(s["relics"],0)
            self.assertEqual(len(s["meta_unlocked"]),1)
            self.assertEqual(s["attack"]>before_attack,mode=="upgrades")
            self.assertEqual(s["potions"]>before_potion,mode=="unlocks")

    def test_high_encounter_budget_is_active_real_finite_reserve(self):
        cfg=make_editor_document("roguelike",
            self.easy(encounters_per_floor=60,foe_attack=0,
                      enemy_patrol=False))["settings"]
        s=start(cfg,0)
        initial=s["map"]["reserve"]
        self.assertGreater(initial,0)
        total=len(s["map"]["enemies"])+initial
        step(s,cfg,"cast_east")
        self.assertEqual(len(s["map"]["enemies"])+s["map"]["reserve"],total)
        self.assertLess(s["map"]["reserve"],initial)
        self.assertLessEqual(len(s["map"]["enemies"]),16)

    def test_signed_floor_rejects_forged_boss_and_impossible_geometry(self):
        settings=self.easy()
        cfg=make_editor_document("roguelike",settings)["settings"]
        scene=make_advanced_scene("roguelike",settings,seed=3)
        self.assertEqual(validate_advanced_scene(scene,settings),scene)
        for mutation in (
            lambda l:l["terrain"].append("floor"),
            lambda l:l["terrain"].__setitem__(0,"wall"),
            lambda l:l["terrain"].__setitem__(1,"pirated_level"),
            lambda l:l["enemies"][0].update(hp=9999),
            lambda l:l["enemies"][0].update(status="defeated"),
            lambda l:l.update(reserve=-1),
            lambda l:l.update(hazard_damage=True),
            lambda l:l.update(script="eval"),
            lambda l:l.update(shop=35),
            lambda l:l["enemies"][0].update(is_boss=True),
        ):
            changed=deepcopy(scene["layout"])
            mutation(changed)
            with self.assertRaises(RoguelikeActionError):
                normalize_layout(cfg,changed)
        modified=deepcopy(scene)
        modified["layout"]["terrain"][1]="wall"
        with self.assertRaises(SceneError):
            validate_advanced_scene(modified,settings)
        with self.assertRaises(SceneError):
            validate_advanced_scene(scene,{**settings,"foe_health":2})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",settings,seed=4,scene=scene)

    def test_save_and_replay_prohibit_fabricated_loot_and_boss_win(self):
        settings=self.easy()
        scene=make_advanced_scene("roguelike",settings,seed=3)
        report=run_advanced_session("roguelike",settings,
                  ["move_east","move_east","inspect"],seed=3,scene=scene)
        self.assertTrue(verify_advanced_session(report,settings))
        save=export_advanced_savegame(report,settings)
        self.assertEqual(import_advanced_savegame(save)["session"],report)
        resumed=continue_advanced_savegame(save,["move_east"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for mutation in (
            lambda s:s.update(floor=99),
            lambda s:s.update(gold=999999),
            lambda s:s.update(victory=True),
            lambda s:s["map"]["enemies"][0].update(hp=0),
            lambda s:s.update(floor_key=True),
        ):
            forged=deepcopy(report)
            mutation(forged["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,settings)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",actions=["inspect"]*129)

    def test_hybrid_assembly_retains_floor_source_and_gameplay_hashes(self):
        cfg=self.easy()
        scene=make_advanced_scene("roguelike",cfg,seed=0)
        assembly=compile_system_assembly("original_rogue",
                        [make_editor_document("roguelike",cfg)],
                        authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"roguelike")
        self.assertEqual(assembly["authored_scene_evidence"][0]["editor"],"roguelike")
        self.assertFalse(assembly["ready_for_release"])

    def test_offline_cli_returns_original_non_native_receipt(self):
        from skeleton.ai.game_builder.system_editor_cli import main
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["play","--editor","roguelike","--seed","1"]),0)
        report=json.loads(output.getvalue())
        self.assertTrue(verify_advanced_session(report))
        self.assertEqual(report["state"]["floor"],1)
        self.assertFalse(report["native_hardware_verified"])
        for bad in ("set_floor:200","force_win","teleport:35",
                    "import_asset:copyright","spawn_gold:999"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("roguelike",actions=[bad])


if __name__=="__main__":
    unittest.main()
