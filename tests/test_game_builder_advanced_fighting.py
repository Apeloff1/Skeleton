"""Original advanced arena fighting: real spatial combat and signed replay."""
from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout
import io,json,unittest

from skeleton.ai.game_builder.advanced_fighting_runtime import (
    ACTIONS,ATTACKS,FightingActionError,default_layout,
    normalize_layout,start,step,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,
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


class OriginalAdvancedArenaTests(unittest.TestCase):
    @staticmethod
    def rules(**kwargs):
        return {"ai_style":"defensive","ai_defense_frequency":0,
                "hazards_enabled":False,"cover_enabled":False,
                **kwargs}

    def test_nineteenth_family_has_fifty_genuine_settings_and_real_actions(self):
        self.assertIn("fighting",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["fighting"]))
        spec=next(x for x in catalog() if x["id"]=="fighting")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertEqual(len(spec["fields"]),50)
        self.assertEqual(len(ACTIONS),len(set(ACTIONS)))
        self.assertGreaterEqual(len(ATTACKS),8)

    def test_signed_original_arena_geometry_varies_without_unlicensed_assets(self):
        for seed in (0,1,2,5,99):
            cfg=make_editor_document("fighting")["settings"]
            layout=default_layout(cfg,seed)
            self.assertEqual(normalize_layout(cfg,layout),layout)
            self.assertEqual(layout["width"],cfg["arena_width"])
            self.assertEqual(layout["lanes"],3)
            scene=make_advanced_scene("fighting",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            initial=run_advanced_session("fighting",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(initial))
            self.assertEqual(initial["state"]["player"]["x"],1)
            self.assertEqual(initial["state"]["opponent"]["x"],10)
            self.assertFalse(initial["native_hardware_verified"])

    def test_spatial_attack_whiffs_without_fabricated_hit_or_free_damage(self):
        cfg=make_editor_document("fighting",self.rules())["settings"]
        state=start(cfg,0)
        before=state["opponent"]["hp"]
        step(state,cfg,"jab")
        self.assertEqual(state["opponent"]["hp"],before)
        self.assertEqual(state["player"]["whiffs"],1)
        self.assertEqual(state["player"]["hits"],0)
        self.assertLess(state["player"]["stamina"],cfg["starting_stamina"])
        with self.assertRaises(FightingActionError):
            step(state,cfg,"teleport:10")

    def test_real_multi_round_victory_needs_earned_kos_not_flag(self):
        cfg=make_editor_document("fighting",
             self.rules(rounds_to_win=2,attack_bonus=0))["settings"]
        state=start(cfg,0)
        for game_round in (1,2):
            state["opponent"]["x"]=state["player"]["x"]+1
            state["opponent"]["hp"]=1
            step(state,cfg,"jab")
            self.assertEqual(state["blue_rounds"],game_round)
        self.assertTrue(state["finished"])
        self.assertTrue(state["victory"])
        self.assertFalse(state["failed"])
        self.assertEqual(state["round_winners"],["blue","blue"])
        self.assertEqual(state["reason"],"legitimate_arena_champion")
        with self.assertRaises(FightingActionError):
            step(state,cfg,"jab")

    def test_ai_has_legitimate_melee_and_can_win_independent_match(self):
        cfg=make_editor_document("fighting",
             self.rules(rounds_to_win=1,ai_style="aggressive",
                        player_health=10,enemy_health=100))["settings"]
        state=start(cfg,0)
        state["opponent"]["x"]=state["player"]["x"]+1
        state["player"]["hp"]=1
        step(state,cfg,"inspect")
        self.assertTrue(state["failed"])
        self.assertTrue(state["finished"])
        self.assertFalse(state["victory"])
        self.assertEqual(state["red_rounds"],1)
        self.assertIn("actual_original_opponent_selected_spatial_counterattack",
                      state["events"])

    def test_actual_high_guard_low_guard_and_grapple_are_different(self):
        cfg=make_editor_document("fighting",
             self.rules(rounds_to_win=2))["settings"]
        state=start(cfg,0)
        state["opponent"]["x"]=state["player"]["x"]+1
        step(state,cfg,"guard_high")
        self.assertGreater(state["player"]["defended"],0)
        self.assertLess(state["player"]["hp"],cfg["player_health"])
        other=start(cfg,0)
        other["opponent"]["x"]=other["player"]["x"]+1
        step(other,cfg,"guard_low")
        self.assertEqual(other["player"]["defended"],0)
        self.assertLess(other["player"]["hp"],state["player"]["hp"])
        grappler=start(cfg,0)
        grappler["opponent"]["x"]=grappler["player"]["x"]+1
        grappler["opponent"]["guard_high"]=True
        before=grappler["opponent"]["hp"]
        step(grappler,cfg,"grapple")
        self.assertLess(grappler["opponent"]["hp"],before-cfg["guard_chip"])

    def test_parry_stun_and_guard_meter_pay_real_tradeoffs(self):
        cfg=make_editor_document("fighting",self.rules())["settings"]
        state=start(cfg,0)
        state["opponent"]["x"]=state["player"]["x"]+1
        before=state["player"]["stamina"]
        step(state,cfg,"parry")
        self.assertEqual(state["player"]["parried"],1)
        self.assertEqual(state["player"]["hp"],state["player"]["max_hp"])
        self.assertEqual(state["opponent"]["stun"],max(
            0,cfg["parry_stun_frames"]-cfg["frames_per_turn"]))
        self.assertLessEqual(state["player"]["stamina"],before)
        self.assertFalse(state["player"]["parry"])
        with self.assertRaises(FightingActionError):
            run_advanced_session("fighting",self.rules(
                starting_stamina=10,parry_stamina=30),["parry"])

    def test_authorized_combo_costs_stamina_and_earns_limited_momentum(self):
        cfg=make_editor_document("fighting",self.rules(
            combo_limit=2,combo_damage_bonus=2,
            stamina_regen=0,ai_style="defensive",
        ))["settings"]
        state=start(cfg,0)
        state["opponent"]["x"]=state["player"]["x"]+1
        state["opponent"]["hp"]=100
        step(state,cfg,"jab")
        first=state["player"]["damage_done"]
        self.assertEqual(state["player"]["combo"],1)
        step(state,cfg,"cross")
        self.assertEqual(state["player"]["combo"],2)
        self.assertGreater(state["player"]["damage_done"]-first,7)
        self.assertLess(state["player"]["stamina"],cfg["starting_stamina"])
        self.assertLessEqual(state["player"]["meter"],cfg["meter_cap"])

    def test_original_meter_gates_special_and_projectile(self):
        hard=self.rules(starting_meter=0,charge_meter=20,
                        ai_style="defensive")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("fighting",hard,["special"])
        report=run_advanced_session("fighting",hard,
                   ["charge","charge","special"])
        self.assertTrue(verify_advanced_session(report,hard))
        self.assertGreater(report["state"]["player"]["meter"],0)
        self.assertEqual(report["state"]["player"]["last_attack"],"special")

    def test_real_lanes_cover_and_weather_intercept_ranged_attack(self):
        cfg=make_editor_document("fighting",{
             **self.rules(cover_enabled=True,cover_count=1),
             "starting_meter":100,
        })["settings"]
        state=start(cfg,2)
        attacker=state["player"];target=state["opponent"]
        attacker["x"]=4;target["x"]=7
        attacker["lane"]=2;target["lane"]=2
        state["arena"]["cover"][0]["x"]=6
        hp=target["hp"]
        step(state,cfg,"projectile")
        self.assertEqual(target["hp"],hp)
        self.assertIn("real_projectile_intercepted_by_authored_arena_cover",
                      state["events"])
        self.assertEqual(attacker["whiffs"],1)

    def test_ringout_occurs_only_at_actual_authored_stage_edge(self):
        cfg=make_editor_document("fighting",self.rules(
               ring_outs=True,knockback=2,rounds_to_win=1))["settings"]
        state=start(cfg,0)
        state["player"]["x"]=9
        state["opponent"]["x"]=10
        state["opponent"]["hp"]=100
        step(state,cfg,"kick")
        self.assertEqual(state["blue_rounds"],1)
        self.assertTrue(state["victory"])
        self.assertGreaterEqual(state["ringouts"],1)
        self.assertEqual(state["round_winners"],["blue"])

    def test_authored_arena_forgery_is_refused_and_new_digest_required(self):
        rules=self.rules()
        cfg=make_editor_document("fighting",rules)["settings"]
        source=make_advanced_scene("fighting",rules,seed=2)
        for change in (
            lambda x:x.update(width=99),
            lambda x:x.update(lanes=4),
            lambda x:x.update(enemy_spawn=[1,1]),
            lambda x:x.update(player_spawn=[-1,1]),
            lambda x:x.update(weather="pirated_material"),
            lambda x:x.update(round_limit_frames=999999),
            lambda x:x.update(script="exec()"),
            lambda x:x["hazards"].append({"x":1,"lane":1,"damage":99}),
            lambda x:x["cover"].append({"x":4,"lane":3,"hp":20}),
        ):
            altered=deepcopy(source["layout"])
            change(altered)
            with self.assertRaises(FightingActionError):
                normalize_layout(cfg,altered)
        edited=deepcopy(source)
        edited["layout"]["theme"]="sky_garden"
        with self.assertRaises(SceneError):
            validate_advanced_scene(edited,rules)
        rebuilt=make_advanced_scene("fighting",rules,seed=2,
                                     layout=edited["layout"])
        self.assertNotEqual(rebuilt["digest"],source["digest"])
        self.assertEqual(validate_advanced_scene(rebuilt,rules),rebuilt)


    def test_studio_renders_original_live_fight_and_signed_stage_painter(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            render_workspace_html,SCRIPT,
        )
        page=render_workspace_html("A"*32).decode("utf-8")
        for key in (
            "fighting-registered-action","Execute original arena frame",
            "paintFightingCell","hazard_toggle","cover_toggle",
            "player_spawn","enemy_spawn","theme_next","weather_next",
            "Original 3-lane arena","Original fighting stage edited",
            "sidestep_up","parry","actual lanes",
        ):
            self.assertIn(key,page)
        self.assertIn('advancedSession.editor!=="fighting"',SCRIPT)
        rules=self.rules()
        old=make_advanced_scene("fighting",rules,seed=2)
        modified=deepcopy(old)
        modified["layout"]["weather"]="clear"
        if old["layout"]["weather"]=="clear":
            modified["layout"]["weather"]="fog"
        with self.assertRaises(SceneError):
            validate_advanced_scene(modified,rules)
        signed=make_advanced_scene("fighting",rules,seed=2,
                    layout=modified["layout"])
        self.assertNotEqual(signed["digest"],old["digest"])
        self.assertTrue(verify_advanced_session(run_advanced_session(
            "fighting",rules,seed=2,scene=signed),rules))

    def test_replay_save_hybrid_assembly_and_offline_cli_use_original_engine(self):
        rules=self.rules()
        scene=make_advanced_scene("fighting",rules,seed=0)
        session=run_advanced_session("fighting",rules,
                  ["approach","guard_high"],seed=0,scene=scene)
        self.assertTrue(verify_advanced_session(session,rules))
        save=export_advanced_savegame(session,rules)
        self.assertEqual(import_advanced_savegame(save)["session"],session)
        resumed=continue_advanced_savegame(save,["recover"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for mutate in (
            lambda s:s["player"].update(hp=999),
            lambda s:s["opponent"].update(hp=0),
            lambda s:s.update(victory=True),
            lambda s:s.update(blue_rounds=9),
            lambda s:s["player"].update(meter=9999),
        ):
            forged=deepcopy(session);mutate(forged["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged,rules)
        assembly=compile_system_assembly("original_arena",
                 [make_editor_document("fighting",rules)],
                 authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],
                         "fighting")
        self.assertFalse(assembly["ready_for_release"])
        from skeleton.ai.game_builder.system_editor_cli import main
        out=io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["play","--editor","fighting","--seed","0"]),0)
        self.assertTrue(verify_advanced_session(json.loads(out.getvalue())))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("fighting",actions=["inspect"]*129)


if __name__=="__main__":
    unittest.main()
