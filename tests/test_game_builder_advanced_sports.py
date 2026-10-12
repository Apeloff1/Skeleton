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
