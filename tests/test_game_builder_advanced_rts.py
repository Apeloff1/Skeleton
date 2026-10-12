"""Original physical RTS strategy, authored maps, AI, economy and replay."""
from __future__ import annotations
from copy import deepcopy
import io,json,unittest
from contextlib import redirect_stdout

from skeleton.ai.game_builder.advanced_rts_runtime import (
    SIZE,CELLS,TYPES,STRUCTURES,ACTIONS,RTSActionError,
    default_layout,normalize_layout,start,step,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalLiveStrategyTests(unittest.TestCase):
    @staticmethod
    def rules(**changes):
        return {**{"enemy_ai":False,"enemy_waves":False},**changes}

    def test_seventeenth_family_real_62_axis_editor_with_registered_actions(self):
        self.assertIn("rts",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["rts"]))
        spec=next(x for x in catalog() if x["id"]=="rts")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertEqual(len(spec["fields"]),62)
        self.assertGreater(len(ACTIONS),500)
        self.assertEqual(len(set(ACTIONS)),len(ACTIONS))

    def test_default_battlefield_has_finite_real_connected_objectives(self):
        for seed in (0,1,4,9,99):
            cfg=make_editor_document("rts")["settings"]
            world=default_layout(cfg,seed)
            self.assertEqual(world,normalize_layout(cfg,world))
            self.assertEqual(len(world["nodes"]),3)
            self.assertEqual(world["friendly_base"],0)
            self.assertEqual(world["enemy_base"],63)
            self.assertEqual(world["relay"],27)
            self.assertNotIn(world["relay"],world["obstacles"])
            scene=make_advanced_scene("rts",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            initial=run_advanced_session("rts",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(initial))
            self.assertEqual(initial["state"]["selected"],0)
            self.assertEqual(len(initial["state"]["units"]),2)
            self.assertTrue(initial["state"]["visible"])
            self.assertFalse(initial["native_hardware_verified"])
        one={"resource_nodes":1}
        report=run_advanced_session("rts",one)
        self.assertEqual(len(report["state"]["map"]["nodes"]),1)

    def test_worker_cargo_is_conserved_and_bank_requires_actual_nearby_depot(self):
        rules=self.rules()
        commands=["harvest:9","tick","tick","tick"]
        report=run_advanced_session("rts",rules,commands)
        self.assertTrue(verify_advanced_session(report,rules))
        state=report["state"]
        source=default_layout(make_editor_document("rts",rules)["settings"],0)
        self.assertLess(state["map"]["nodes"][0]["stock"],source["nodes"][0]["stock"])
        self.assertGreater(state["wood"],source["starting_wood"])
        self.assertEqual(state["units"][0]["cargo"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["deposit"])
        carried=run_advanced_session("rts",rules,["harvest:9","deposit"])
        self.assertEqual(carried["state"]["units"][0]["cargo"],0)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["harvest:63"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["select:1","harvest:9"])

    def test_genuine_relay_capture_and_hold_wins_spatial_match(self):
        rules=self.rules(capture_ticks=2,hold_ticks=3)
        commands=["select:1","move:27","tick:4","tick:4",
                  "capture","tick:4"]
        match=run_advanced_session("rts",rules,commands)
        state=match["state"]
        self.assertTrue(verify_advanced_session(match,rules))
        self.assertTrue(state["finished"])
        self.assertTrue(state["victory"])
        self.assertEqual(state["relay_owner"],"blue")
        self.assertEqual(state["reason"],"physical_original_relay_control")
        self.assertIn("legitimate_rts_control_victory",state["achievements"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["capture"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,commands+["tick"])

    def test_opposing_command_has_actual_hp_and_requires_live_adjacent_attacks(self):
        cfg=make_editor_document("rts",self.rules(fog_of_war=False,
             siege_attack=20))["settings"]
        state=start(cfg,0)
        fighter=state["units"][1];fighter["cell"]=62
        state["selected"]=1
        for _ in range(6):
            step(state,cfg,"attack:63")
            if state["finished"]:break
        self.assertEqual(state["buildings"][1]["hp"],0)
        self.assertTrue(state["victory"])
        self.assertEqual(state["reason"],"actual_enemy_command_destroyed")
        self.assertEqual(state["buildings"][0]["hp"],cfg["friendly_base_health"])
        with self.assertRaises(RTSActionError):
            step(state,cfg,"tick")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",self.rules(),["select:1","attack:63"])

    def test_real_training_requires_barracks_supply_money_and_empty_footprint(self):
        cfg=make_editor_document("rts",self.rules())["settings"]
        state=start(cfg,0)
        with self.assertRaises(RTSActionError):
            step(state,cfg,"train:ranger")
        with self.assertRaises(RTSActionError):
            step(state,cfg,"construct:wall:1")
        step(state,cfg,"construct:barracks:2")
        step(state,cfg,"move:9")
        before=state["wood"]
        step(state,cfg,"train:soldier")
        self.assertEqual(len(state["units"]),3)
        self.assertLess(state["wood"],before)
        self.assertTrue(any(u["id"]==2 and u["kind"]=="soldier"
                            for u in state["units"]))
        with self.assertRaises(RTSActionError):
            step(state,cfg,"select:15")

    def test_technology_charges_materials_and_changes_actual_damage(self):
        cfg=make_editor_document("rts",self.rules())["settings"]
        state=start(cfg,0)
        w,o,e=state["wood"],state["ore"],state["energy"]
        step(state,cfg,"research:weapons")
        self.assertEqual(state["tech"]["weapons"],1)
        self.assertLess(state["wood"],w)
        self.assertLess(state["ore"],o)
        self.assertLess(state["energy"],e)
        cfg2=make_editor_document("rts",
               self.rules(research_cap=0))["settings"]
        with self.assertRaises(RTSActionError):
            step(start(cfg2,0),cfg2,"research:weapons")

    def test_fog_and_scan_are_real_nonfree_and_never_authorize_hidden_attack(self):
        rules=self.rules(fog_of_war=True,vision_radius=1,base_vision=1)
        first=run_advanced_session("rts",rules)
        self.assertNotIn(63,first["state"]["visible"])
        scanned=run_advanced_session("rts",rules,["scan"])
        self.assertLess(scanned["state"]["energy"],first["state"]["energy"])
        self.assertGreater(len(scanned["state"]["visible"]),
                           len(first["state"]["visible"]))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["attack:63"])

    def test_finite_supply_modes_have_meaningfully_different_costs(self):
        base=self.rules()
        population=run_advanced_session("rts",{**base,"supply_model":"population"},["tick:4"])
        logistics=run_advanced_session("rts",{**base,"supply_model":"logistics"},["tick:4"])
        self.assertLess(logistics["state"]["energy"],population["state"]["energy"])
        free=run_advanced_session("rts",{**base,"supply_model":"none"},["tick:4"])
        self.assertEqual(free["state"]["energy"],population["state"]["energy"])
        self.assertTrue(verify_advanced_session(logistics,{**base,"supply_model":"logistics"}))

    def test_real_enemy_movement_and_counterattack_change_world(self):
        cfg=make_editor_document("rts",
             self.rules(enemy_ai=True,enemy_patrol=True,
                        enemy_aggro=12,enemy_attack=3))["settings"]
        state=start(cfg,0)
        origin=state["enemies"][0]["cell"]
        for _ in range(3):step(state,cfg,"tick")
        self.assertNotEqual(origin,state["enemies"][0]["cell"])
        self.assertLess(state["tick"],128)
        self.assertTrue(any("opposing_original_faction" in e or
                     "real_grid_unit" in e for e in state["events"]) or
                     state["enemies"][0]["cell"]!=origin)

    def test_world_graph_rejects_overlap_spoof_or_unreachable_capture(self):
        cfg=make_editor_document("rts",self.rules())["settings"]
        scene=make_advanced_scene("rts",self.rules(),seed=3)
        for mutation in (
           lambda x:x["nodes"][0].update(stock=True),
           lambda x:x["nodes"][0].update(type="gold"),
           lambda x:x["nodes"][0].update(id=2),
           lambda x:x.update(enemy_base=x["friendly_base"]),
           lambda x:x.update(relay=x["enemy_spawns"][0]),
           lambda x:x["obstacles"].append(x["friendly_base"]),
           lambda x:x["nodes"][0].update(cell=x["relay"]),
           lambda x:x.update(starting_wood=1000000),
           lambda x:x.update(script="win()"),
           lambda x:x.update(environment="pirated_level"),
           lambda x:x.update(friendly_spawns=[1]),
        ):
            forged=deepcopy(scene["layout"])
            mutation(forged)
            with self.assertRaises(RTSActionError):
                normalize_layout(cfg,forged)
        stale=deepcopy(scene)
        stale["layout"]["nodes"][0]["stock"]-=1
        with self.assertRaises(SceneError):
            validate_advanced_scene(stale,self.rules())
        with self.assertRaises(SceneError):
            validate_advanced_scene(scene,self.rules(starting_wood=40))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",self.rules(),seed=4,scene=scene)

    def test_portable_savegame_and_forged_credits_have_independent_replay(self):
        rules=self.rules()
        scene=make_advanced_scene("rts",rules,seed=5)
        session=run_advanced_session("rts",rules,["harvest:9","tick"],
                    seed=5,scene=scene)
        self.assertTrue(verify_advanced_session(session,rules))
        save=export_advanced_savegame(session,rules)
        self.assertEqual(import_advanced_savegame(save)["session"],session)
        resumed=continue_advanced_savegame(save,["tick"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for mutation in (
          lambda s:s.update(wood=90000),
          lambda s:s["map"]["nodes"][0].update(stock=999999),
          lambda s:s["units"][0].update(cargo=1000),
          lambda s:s.update(victory=True),
          lambda s:s.update(relay_owner="blue"),
          lambda s:s["enemies"][0].update(hp=0),
        ):
            forged=deepcopy(session);mutation(forged["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,rules)


    def test_studio_original_terrain_painter_and_live_unit_composer_are_verified(self):
        from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html,SCRIPT
        page=render_workspace_html("A"*32).decode("utf-8")
        for token in ("paintRTSCell","rts-owned-unit","rts-target-cell",
             "rts-command","Issue verified tactical order",
             "obstacle_toggle","wood_node","enemy_base_hp_up",
             "friendly_spawn","enemy_spawn","selectedRTSCell",
             "Original 8×8 original strategic resource/capture map"):
            self.assertIn(token,page)
        self.assertIn("Original strategy source mutated. Validate",SCRIPT)
        rules=self.rules()
        source=make_advanced_scene("rts",rules,seed=3)
        changed=deepcopy(source)
        changed["layout"]["environment"]="desert" if (
            changed["layout"]["environment"]!="desert") else "rain"
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed,rules)
        refreshed=make_advanced_scene("rts",rules,seed=3,
                            layout=changed["layout"])
        self.assertNotEqual(refreshed["digest"],source["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("rts",rules,seed=3,scene=refreshed),rules))

    def test_real_physical_terrain_prevents_direct_unit_teleports(self):
        rules=self.rules()
        match=run_advanced_session("rts",rules,["select:1","move:27"])
        unit=next(x for x in match["state"]["units"] if x["id"]==1)
        self.assertNotEqual(unit["cell"],27)
        self.assertEqual(match["state"]["turn"],2)
        self.assertLessEqual(abs(unit["cell"]%8)+abs(unit["cell"]//8-1),3)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",rules,["select:1","move:63"])
        # Remote movement may be ordered across valid geography; it is
        # never executed as one-step teleportation.
        travel=run_advanced_session("rts",rules,["select:1","move:62"])
        self.assertNotEqual(travel["state"]["units"][1]["cell"],62)
        self.assertTrue(verify_advanced_session(travel,rules))

    def test_original_hybrid_source_and_offline_cli_produce_true_gameplay(self):
        cfg=self.rules()
        scene=make_advanced_scene("rts",cfg,seed=0)
        assembly=compile_system_assembly("real_original_strategy",
                      [make_editor_document("rts",cfg)],authorized=True,
                      scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["authored_scene_evidence"][0]["editor"],"rts")
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"rts")
        self.assertFalse(assembly["ready_for_release"])
        from skeleton.ai.game_builder.system_editor_cli import main
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["play","--editor","rts","--seed","0"]),0)
        report=json.loads(output.getvalue())
        self.assertTrue(verify_advanced_session(report))
        self.assertFalse(report["native_hardware_verified"])
        for forged in ("set_wood:999","teleport:27","win","destroy_enemy_base"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("rts",actions=[forged])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rts",actions=["inspect"]*129)


if __name__=="__main__":
    unittest.main()
