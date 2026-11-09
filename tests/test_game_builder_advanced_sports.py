"""Four distinct original sports references: earned scoring and forged-replay refusal."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_sports_runtime import (
    ACTIONS, MODES, MODE_ACTIONS, SportsActionError,
    default_layout, normalize_layout, start, step,
)
from skeleton.ai.game_builder.system_editors import (
    catalog, make_editor_document, SystemEditorError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, AdvancedRuntimeError,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene, SceneError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalSportsRulesTests(unittest.TestCase):
    def test_four_distinct_playable_modes_have_typed_controls(self):
        self.assertIn("sports", ENGINES)
        self.assertEqual(set(ACTIONS), set(ACTION_HELP["sports"]))
        spec=next(x for x in catalog() if x["id"]=="sports")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]),30)
        self.assertEqual(len(MODES),4)
        self.assertEqual(len({frozenset(v) for v in MODE_ACTIONS.values()}),4)
        for mode in MODES:
            params={"rules":mode}
            if mode=="racket":
                params.update(team_size=2,substitutions=0)
            game=run_advanced_session("sports",params,["inspect"],seed=1)
            self.assertEqual(game["state"]["mode"],mode)
            self.assertTrue(verify_advanced_session(game,params))

    def test_authored_stadium_is_source_bound_and_mode_consistent(self):
        for mode in MODES:
            params={"rules":mode}
            if mode=="racket":
                params.update(team_size=2,substitutions=0)
            rules=make_editor_document("sports",params)["settings"]
            for seed in (0,1,5):
                layout=default_layout(rules,seed)
                self.assertEqual(normalize_layout(rules,layout),layout)
                scene=make_advanced_scene("sports",params,seed=seed)
                self.assertEqual(validate_advanced_scene(scene,params),scene)
                proof=run_advanced_session("sports",params,seed=seed,scene=scene)
                self.assertTrue(verify_advanced_session(proof,params))
                self.assertFalse(proof["publication_certified"])
                self.assertFalse(proof["native_hardware_verified"])

    def test_team_field_goal_requires_real_authored_position(self):
        params={"target_score":1}
        off_target=run_advanced_session("sports",params,["shoot"])
        self.assertEqual(off_target["state"]["home_score"],0)
        self.assertEqual(off_target["state"]["misses"],1)
        rules=make_editor_document("sports",params)["settings"]
        level=default_layout(rules,0)
        level["home_spawn"]=[85,1]
        scene=make_advanced_scene("sports",params,layout=level)
        goal=run_advanced_session("sports",params,["shoot"],scene=scene)
        self.assertEqual(goal["state"]["home_score"],1)
        self.assertTrue(goal["state"]["victory"])
        self.assertTrue(goal["state"]["finished"])
        self.assertIn("earned_home_point",goal["state"]["events"])
        self.assertTrue(verify_advanced_session(goal,params))

    def test_racket_points_require_actual_serves_and_winning_shots(self):
        params={"rules":"racket","team_size":2,"substitutions":0,"target_score":2}
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sports",params,["smash"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sports",params,["serve","serve"])
        proof=run_advanced_session("sports",params,
                                   ["serve","smash","serve","smash"],seed=0)
        self.assertEqual(proof["state"]["home_score"],2)
        self.assertEqual(proof["state"]["shots"],2)
        self.assertTrue(proof["state"]["victory"])
        self.assertTrue(verify_advanced_session(proof,params))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sports",params,["tackle"])

    def test_arena_contact_and_goal_really_affect_game_state(self):
        params={"rules":"arena","target_score":1}
        cfg=make_editor_document("sports",params)["settings"]
        state=start(cfg,0)
        events=step(state,cfg,"carry")
        self.assertIn("player_field_position_changed",events)
        self.assertGreater(state["home"][0],2)
        level=default_layout(cfg,0)
        level["home_spawn"]=[85,1]
        scene=make_advanced_scene("sports",params,layout=level)
        goal=run_advanced_session("sports",params,["score"],scene=scene)
        self.assertTrue(goal["state"]["victory"])
        self.assertTrue(goal["state"]["finished"])

    def test_turn_based_actions_require_finite_action_point_commit(self):
        params={"rules":"turn_based","action_points":2}
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sports",params,["move","move","move"])
        report=run_advanced_session("sports",params,
                                    ["move","move","end_turn","move"])
        self.assertEqual(report["state"]["turns_committed"],1)
        self.assertEqual(report["state"]["ap_remaining"],1)
        self.assertTrue(verify_advanced_session(report,params))

    def test_sports_scene_and_receipt_cannot_award_forged_scores(self):
        scene=make_advanced_scene("sports")
        changed=deepcopy(scene)
        changed["layout"]["mode"]="racket"
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed)
        changed=deepcopy(scene)
        changed["layout"]["target_score"]=1
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed)
        proof=run_advanced_session("sports",actions=["advance","pass"],scene=scene)
        forged=deepcopy(proof)
        forged["state"]["home_score"]=999
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged)
        source=make_editor_document("sports")
        assembly=compile_system_assembly("original_stadium",[source],
                                         authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"sports")

    def test_pass_is_control_transfer_not_ball_carrier_teleport(self):
        cfg=make_editor_document("sports")["settings"]
        state=start(cfg,0)
        initial=list(state["home"])
        receiver=list(state["teammate"])
        self.assertNotEqual(initial,receiver)
        events=step(state,cfg,"pass")
        self.assertIn("earned_ball_transfer_to_existing_teammate",events)
        self.assertEqual(state["home"],receiver)
        self.assertEqual(state["teammate"],initial)
        self.assertEqual(state["ball"],receiver)
        self.assertEqual(state["passes"],1)
        self.assertEqual(state["owner"],"home")
        single=make_editor_document("sports",{"team_size":1,"substitutions":0})["settings"]
        with self.assertRaises(SportsActionError):
            step(start(single,0),single,"pass")

    def test_authored_cover_blocks_real_pass_and_unearned_goal(self):
        cfg=make_editor_document("sports")["settings"]
        layout=default_layout(cfg,0)
        layout["home_spawn"]=[40,1]
        layout["cover"]=[[42,1]]
        scene=make_advanced_scene("sports",layout=layout)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("sports",actions=["pass"],scene=scene)
        self.assertTrue(verify_advanced_session(
            run_advanced_session("sports",actions=["advance"],scene=scene)))

    def test_weather_and_press_actually_affect_dynamics(self):
        config={"target_score":1,"shot_power":4,"opponent_skill":8}
        cfg=make_editor_document("sports",config)["settings"]
        clear=default_layout(cfg,0)
        rain=deepcopy(clear);rain["weather"]="rain"
        wind=deepcopy(clear);wind["weather"]="wind"
        clear_scene=make_advanced_scene("sports",config,layout=clear)
        rain_scene=make_advanced_scene("sports",config,layout=rain)
        dry=run_advanced_session("sports",config,["sprint"],scene=clear_scene)
        wet=run_advanced_session("sports",config,["sprint"],scene=rain_scene)
        self.assertGreater(dry["state"]["home"][0],wet["state"]["home"][0])
        self.assertTrue(verify_advanced_session(wet,config))
        for layout in (clear,wind):
            layout["home_spawn"]=[85,1]
        calm_scene=make_advanced_scene("sports",config,layout=clear)
        gust_scene=make_advanced_scene("sports",config,layout=wind)
        calm=run_advanced_session("sports",config,["shoot"],scene=calm_scene)
        gust=run_advanced_session("sports",config,["shoot"],scene=gust_scene)
        self.assertEqual(calm["state"]["home_score"],1)
        self.assertEqual(gust["state"]["home_score"],0)
        self.assertTrue(verify_advanced_session(gust,config))

    def test_swept_collision_uses_nearest_wall_not_json_order(self):
        cfg=make_editor_document("sports")["settings"]
        layout=default_layout(cfg,0)
        layout["home_spawn"]=[8,1]
        layout["cover"]=[[16,1],[12,1]]
        course=make_advanced_scene("sports",layout=layout)
        trial=run_advanced_session("sports",actions=["sprint"],scene=course)
        self.assertEqual(trial["state"]["home"],[11,1])
        self.assertTrue(verify_advanced_session(trial))
        swapped=deepcopy(layout)
        swapped["cover"].reverse()
        swapped_course=make_advanced_scene("sports",layout=swapped)
        swapped_trial=run_advanced_session("sports",actions=["sprint"],
                                           scene=swapped_course)
        self.assertEqual(swapped_trial["state"]["home"],[11,1])
        self.assertTrue(verify_advanced_session(swapped_trial))

    def test_defender_really_intercepts_swept_teammate_pass(self):
        cfg=make_editor_document("sports")["settings"]
        layout=default_layout(cfg,0)
        layout["home_spawn"]=[40,1]
        layout["away_spawn"]=[43,1]
        layout["cover"]=[]
        scene=make_advanced_scene("sports",layout=layout)
        attempt=run_advanced_session("sports",actions=["pass"],scene=scene)
        self.assertEqual(attempt["state"]["owner"],"away")
        self.assertEqual(attempt["state"]["home"],[40,1])
        self.assertEqual(attempt["state"]["interceptions"],1)
        self.assertIn("defender_intercepted_swept_pass",
                      attempt["state"]["events"])
        self.assertTrue(verify_advanced_session(attempt))

    def test_tactical_mode_goal_is_actually_earned(self):
        settings={"rules":"turn_based","target_score":1,"action_points":2}
        rules=make_editor_document("sports",settings)["settings"]
        layout=default_layout(rules,0)
        layout["home_spawn"]=[85,1]
        scene=make_advanced_scene("sports",settings,layout=layout)
        victory=run_advanced_session("sports",settings,
                                     ["shoot"],scene=scene)
        self.assertTrue(victory["state"]["finished"])
        self.assertTrue(victory["state"]["victory"])
        self.assertEqual(victory["state"]["home_score"],1)
        self.assertEqual(victory["state"]["ap_remaining"],1)
        self.assertTrue(verify_advanced_session(victory,settings))

    def test_authored_match_clock_records_draw_and_full_period_lifecycle(self):
        settings={"match_minutes":80,"match_turn_limit":20,"opponent_speed":1}
        timeline=run_advanced_session("sports",settings,["inspect"]*20)
        self.assertTrue(timeline["state"]["finished"])
        self.assertFalse(timeline["state"]["victory"])
        self.assertTrue(timeline["state"]["draw"])
        self.assertEqual(timeline["state"]["winner"],"draw")
        self.assertEqual(timeline["state"]["elapsed_minutes"],80)
        self.assertEqual(timeline["state"]["period"],4)
        self.assertEqual(timeline["state"]["tick"],20)
        self.assertTrue(verify_advanced_session(timeline,settings))
        first=run_advanced_session("sports",settings,["inspect"]*5)
        self.assertEqual(first["state"]["elapsed_minutes"],20)
        self.assertEqual(first["state"]["period"],2)
        self.assertFalse(first["state"]["finished"])

    def test_fail_closed_cross_rules_and_impossible_team_rosters(self):
        for params in (
            {"rules":"racket"},
            {"team_size":1,"substitutions":5},
            {"run_speed":15,"sprint_speed":2},
            {"field_length":10,"shot_range":18},
            {"rules":"unlicensed_league"},
            {"target_score":True},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("sports",params)


if __name__=="__main__":
    unittest.main()
