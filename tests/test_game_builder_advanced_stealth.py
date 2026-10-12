"""Executable mission, authoring and security adversarial contracts for original stealth."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_stealth_runtime import (
    ACTIONS, WIDTH, HEIGHT, StealthActionError, _line_of_sight,
    default_layout, normalize_layout, start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame,
    continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly
from skeleton.ai.game_builder.system_editors import make_editor_document, catalog


class OriginalStealthReferenceTests(unittest.TestCase):
    def test_thirty_four_advanced_controls_and_playable_action_registry(self):
        self.assertIn("stealth",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["stealth"]))
        self.assertGreater(len(ACTIONS),20)
        specs={s["id"]:s for s in catalog()}
        self.assertEqual(len(specs["stealth"]["fields"]),34)
        self.assertEqual(specs["stealth"]["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(specs["stealth"]["progression_floor"],"advanced")

    def test_real_keycard_heist_via_original_corridors_and_terminal_extraction(self):
        config={"guard_count":0,"camera_range":0}
        route=(["move_east"]*2+["collect_keycard"]+["move_east"]*6+
               ["steal","move_east"]+["move_south"]*7+["extract"])
        result=run_advanced_session("stealth",config,route)
        self.assertTrue(verify_advanced_session(result,config))
        state=result["state"]
        self.assertTrue(result["terminal"])
        self.assertTrue(state["finished"])
        self.assertTrue(state["archive"])
        self.assertTrue(state["extracted"])
        self.assertEqual(state["keycards_owned"],1)
        self.assertEqual(state["player"],[9,7])
        self.assertIn("authoritative_original_infiltration_complete",state["milestones"])
        self.assertGreater(state["score"],100)
        self.assertFalse(result["native_hardware_verified"])

    def test_player_cannot_teleport_steal_or_bypass_physical_doors(self):
        for action in ("steal","extract","collect_keycard","hack_terminal",
                       "hack_door","neutralize","hide","disguise","infinite_gadget"):
            with self.subTest(action=action):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("stealth",{"guard_count":0},[action])
        # A wall blocks the lower corridor unless player routes through
        # the genuine map; an authored vent accepts crouched entry only.
        layout=default_layout(make_editor_document("stealth")["settings"],0)
        self.assertEqual(layout["doors"],[[3,4],[6,5]])
        state=start(make_editor_document("stealth")["settings"],0)
        state["player"]=[2,7]
        self.assertRaises(StealthActionError,step,state,
                          make_editor_document("stealth")["settings"],"move_east")
        step(state,make_editor_document("stealth")["settings"],"crouch_east")
        self.assertEqual(state["player"],[3,7])
        self.assertTrue(state["crouched"])

    def test_acoustic_security_and_actual_cover_change_risk(self):
        cfg=make_editor_document("stealth",{
            "suspicion_threshold":20,"guard_count":8,
            "detection_gain":30,"noise_gain":20,"camera_range":0,
        })["settings"]
        silent=start(cfg,0)
        step(silent,cfg,"crouch_east")
        loud=start(cfg,0)
        step(loud,cfg,"sprint_east")
        self.assertGreater(loud["alarm"],silent["alarm"])
        self.assertTrue(any("noise" in e for e in loud["events"]))
        self.assertLess(loud["stamina"],silent["stamina"])
        self.assertTrue(_line_of_sight(loud,[0,0],[2,0]))
        self.assertFalse(_line_of_sight(loud,[2,1],[4,1])) # authored wall (3,1)

    def test_finite_smoke_decoys_hacks_and_debt_free_medkits(self):
        cfg=make_editor_document("stealth",{"guard_count":0,"camera_range":0})["settings"]
        state=start(cfg,0)
        step(state,cfg,"deploy_smoke")
        self.assertEqual(state["smoke_turns"],cfg["smoke_duration"]-1)
        self.assertEqual(state["smoke_charges"],cfg["smoke_charges"]-1)
        step(state,cfg,"deploy_emp")
        self.assertEqual(state["emp_charges"],0)
        self.assertRaises(StealthActionError,step,state,cfg,"deploy_emp")
        self.assertRaises(StealthActionError,step,state,cfg,"use_medkit")
        for _ in range(cfg["stun_charges"]):
            step(state,cfg,"decoy_north")
        self.assertRaises(StealthActionError,step,state,cfg,"decoy_east")

    def test_mission_types_protect_goals_and_no_fake_win(self):
        # A mission type changes what constitutes legal extraction.
        for mission in ("archive","sabotage","intelligence"):
            cfg={"guard_count":0,"camera_range":0,"mission":mission}
            state=run_advanced_session("stealth",cfg,["wait","rest"])
            self.assertFalse(state["state"]["finished"])
            self.assertEqual(state["state"]["score"],0)
        for key,val in (("mission","elevate_to_admin"),
                        ("guard_count",-1),("stamina",True),
                        ("alarm_gain",9999)):
            with self.assertRaises(ValueError):
                make_editor_document("stealth",{key:val})

    def test_authored_missions_sealed_reachable_and_non_executable(self):
        config={"guard_count":3}
        scene=make_advanced_scene("stealth",config,seed=12)
        self.assertEqual(validate_advanced_scene(scene,config),scene)
        for mutate in (
            lambda x:x["layout"].update(spawn=[-1,2]),
            lambda x:x["layout"]["walls"].append([8,1]),
            lambda x:x["layout"]["guard_routes"].__setitem__(0,[[3,1],[4,1]]),
            lambda x:x["layout"].update(eval_python="import os"),
            lambda x:x["layout"].update(alarm_budget=True),
            lambda x:x["layout"].update(lighting="javascript:"),
            lambda x:x.update(seed=13),
            lambda x:x.update(digest="0"*64),
            lambda x:x["layout"].update(walls=[[1,y] for y in range(8)]),
        ):
            forged=deepcopy(scene)
            mutate(forged)
            with self.assertRaises((SceneError,StealthActionError)):
                validate_advanced_scene(forged,config)
        original=make_advanced_scene("stealth",config,seed=12)
        self.assertEqual(run_advanced_session(
            "stealth",config,["wait"],seed=12,scene=original)["scene_digest"],
            original["digest"])

    def test_intelligence_and_sabotage_must_have_finite_targets(self):
        base=make_editor_document("stealth")["settings"]
        original=default_layout(base,0)
        with self.assertRaises(StealthActionError):
            normalize_layout({**base,"mission":"intelligence","intel_target":3},original)
        altered=deepcopy(original)
        altered["cameras"]=[]
        with self.assertRaises(StealthActionError):
            normalize_layout({**base,"mission":"sabotage"},altered)
        altered=deepcopy(original)
        altered["keycards"]=[]
        with self.assertRaises(StealthActionError):
            normalize_layout({**base,"mission":"archive","hacking_charges":0},altered)

    def test_receipt_forgery_and_save_continue_do_not_promote_cheats(self):
        config={"guard_count":0,"camera_range":0}
        scene=make_advanced_scene("stealth",config,seed=5)
        session=run_advanced_session("stealth",config,
                                     ["move_east","move_east","collect_keycard"],
                                     seed=5,scene=scene)
        save=export_advanced_savegame(session,config)
        self.assertEqual(import_advanced_savegame(save)["session"],session)
        following=continue_advanced_savegame(save,["move_east"])
        self.assertTrue(import_advanced_savegame(following)["verified"])
        for field,new in (("score",10000000),("archive",True),("alarm",90),
                          ("finished",True),("keycards_owned",20)):
            altered=deepcopy(session)
            altered["state"][field]=new
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(altered,config)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("stealth",config,["wait"]*129)


    def test_reachable_sabotage_and_intelligence_have_distinct_real_objectives(self):
        security={"guard_count":0,"camera_range":0,"mission":"sabotage"}
        # Reach a live surveillance device, then its actual security console.
        sab=(["move_east"]*8+["move_south"]*2+["disable_camera"]
             +["move_south"]*2+["move_west","hack_terminal"]
             +["move_south"]*3+["move_east"]*2+["extract"])
        sabotaged=run_advanced_session("stealth",security,sab)
        self.assertTrue(sabotaged["state"]["finished"])
        self.assertTrue(sabotaged["state"]["terminal_hacked"])
        self.assertEqual(sabotaged["state"]["cameras_disabled"],1)
        self.assertTrue(verify_advanced_session(sabotaged,security))
        intelligence={"guard_count":0,"camera_range":0,"mission":"intelligence"}
        dossier=(["move_east"]*5+["collect_intel"]+["move_east"]*2
                +["move_south"]*7+["collect_intel"]+["move_east"]*2
                +["extract"])
        intel=run_advanced_session("stealth",intelligence,dossier)
        self.assertTrue(intel["state"]["finished"])
        self.assertEqual(intel["state"]["intel_collected"],2)
        self.assertTrue(verify_advanced_session(intel,intelligence))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("stealth",security,["extract"])

    def test_actual_reserve_agents_deploy_under_alarm_without_250_actors_on_80_cells(self):
        cfg=make_editor_document("stealth",{
            "guard_count":150,"suspicion_threshold":1,
            "alarm_gain":50,"alarm_cooldown":0,
            "noise_gain":20,"fail_on_alarm":False,
            "alarm_damage":0,"contact_damage":0,
            "reinforcement_interval":1,
        })["settings"]
        state=start(cfg,0)
        self.assertEqual(len(state["guards"]),8)
        self.assertEqual(state["guard_reserve"],142)
        for _ in range(6):
            if state["failed"]:break
            step(state,cfg,"decoy_east" if state["stun_charges"] else "wait")
        self.assertGreater(state["reinforcements_deployed"],0)
        self.assertEqual(state["guard_reserve"]+
                         state["reinforcements_deployed"],142)
        self.assertLessEqual(len(state["guards"]),20)

    def test_local_studio_has_visual_infiltration_map_and_supervised_patrol_source(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            SCRIPT,render_workspace_html,
        )
        source=render_workspace_html("A"*32).decode("utf-8")
        for piece in ("paintStealthCell","patrol_route",
                      "guard_routes","Stealth geography changed",
                      "stealth-player-command",
                      "Execute verified stealth action",
                      "ArrowUp","crouch","sprint","Original infiltration 10×8"):
            self.assertIn(piece,source)
        self.assertIn("paintStealthCell",SCRIPT)
        initial=make_advanced_scene("stealth",seed=3)
        draft=deepcopy(initial)
        draft["layout"]["lighting"]="night"
        with self.assertRaises(SceneError):
            validate_advanced_scene(draft)
        signed=make_advanced_scene("stealth",seed=3,layout=draft["layout"])
        self.assertNotEqual(signed["digest"],initial["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("stealth",seed=3,scene=signed)))


    def test_ai_planner_rehearses_three_real_missions_without_certifying_guard_evasion(self):
        from skeleton.ai.game_builder.advanced_stealth_planner import plan_stealth_route
        for mission in ("archive","sabotage","intelligence"):
            config={"mission":mission,"guard_count":8}
            scene=make_advanced_scene("stealth",config,seed=0)
            proof=plan_stealth_route(scene,config,max_states=60000,max_depth=96)
            with self.subTest(mission=mission):
                self.assertEqual(proof["feasibility"],"rehearsal_route_found")
                self.assertTrue(proof["route"])
                self.assertEqual(proof["route"][-1],"extract")
                self.assertTrue(proof["rehearsal_verified"])
                self.assertEqual(len(proof["rehearsal_session_digest"]),64)
                self.assertEqual(proof["scene_digest"],scene["digest"])
                self.assertFalse(proof["actual_security_evasion_verified"])
                self.assertFalse(proof["native_engine_verified"])
                self.assertFalse(proof["source_mutated"])
                self.assertEqual(proof,plan_stealth_route(
                    scene,config,max_states=60000,max_depth=96))

    def test_planner_rejects_opaque_forged_scenes_and_unbounded_search(self):
        from skeleton.ai.game_builder.advanced_stealth_planner import (
            plan_stealth_route,StealthPlanningError,
        )
        scene=make_advanced_scene("stealth",seed=0)
        for bad in (0,True,199,150001):
            with self.assertRaises(StealthPlanningError):
                plan_stealth_route(scene,max_states=bad)
        for bad in (0,True,129):
            with self.assertRaises(StealthPlanningError):
                plan_stealth_route(scene,max_depth=bad)
        forged=deepcopy(scene)
        forged["layout"]["spawn"]=[9,7]
        with self.assertRaises(SceneError):
            plan_stealth_route(forged)
        with self.assertRaises(SceneError):
            plan_stealth_route(scene,{"mission":"intelligence"})

    def test_studio_and_cli_expose_actual_bounded_staged_rehearsals(self):
        import json,io,tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from skeleton.ai.game_builder.system_editor_cli import main
        from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
        scene=make_advanced_scene("stealth",seed=0)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"scene.json"
            path.write_text(json.dumps(scene),encoding="utf-8")
            output=io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["plan-stealth","--scene",str(path),
                                        "--max-states","60000"]),0)
            proof=json.loads(output.getvalue())
            self.assertTrue(proof["rehearsal_verified"])
            self.assertFalse(proof["source_mutated"])
        page=render_workspace_html("A"*32).decode("utf-8")
        for text in ("stealth-mission-plan","stealth-plan-proof",
                     "/api/stealth-plan","rehearsal_verified",
                     "actual_security_evasion_verified"):
            self.assertIn(text,page)

    def test_hybrid_assembly_uses_genuine_stealth_scene_and_replay(self):
        scene=make_advanced_scene("stealth",seed=0)
        assembly=compile_system_assembly("original_infiltration",
                    [make_editor_document("stealth")],authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"stealth")
        self.assertEqual(assembly["authored_scene_evidence"][0]["editor"],"stealth")
        self.assertFalse(assembly["ready_for_release"])


if __name__=="__main__":
    unittest.main()
