"""Replay-grade AI coach must prove real points in all four original sports."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_sports_runtime import MODES,default_layout
from skeleton.ai.game_builder.advanced_sports_coach import (
    COACH_ACTIONS,SportsPlanningError,
    plan_original_sports_match,verify_original_sports_plan,
)
from skeleton.ai.game_builder.system_editors import make_editor_document


class OriginalSportsCoachTests(unittest.TestCase):
    @staticmethod
    def near_goal(mode):
        settings={"rules":mode,"target_score":1}
        if mode=="racket":
            settings.update(team_size=2,substitutions=0)
        cfg=make_editor_document("sports",settings)["settings"]
        layout=default_layout(cfg,0)
        if mode!="racket":
            layout["home_spawn"]=[85,1]
        return settings,make_advanced_scene("sports",settings,layout=layout)

    def test_verified_winning_strategies_for_all_four_original_sports(self):
        self.assertEqual(set(COACH_ACTIONS),set(MODES))
        for mode in MODES:
            with self.subTest(mode=mode):
                settings,scene=self.near_goal(mode)
                plan=plan_original_sports_match(scene,settings,max_states=128,
                                                max_depth=5,beam_width=20)
                self.assertEqual(plan["status"],"replay_verified_win")
                self.assertTrue(plan["independently_verified"])
                self.assertFalse(plan["native_hardware_certified"])
                self.assertFalse(plan["publication_certified"])
                self.assertEqual(plan["rules"],mode)
                self.assertTrue(verify_original_sports_plan(plan,scene,settings))
                proof=run_advanced_session("sports",settings,plan["actions"],
                                            seed=scene["seed"],scene=scene)
                self.assertTrue(proof["state"]["finished"])
                self.assertTrue(proof["state"]["victory"])
                self.assertGreater(proof["state"]["home_score"],
                                   proof["state"]["away_score"])
                self.assertTrue(verify_advanced_session(proof,settings))
                self.assertEqual(plan["original_replay_digest"],proof["digest"])

    def test_finite_search_never_launders_inconclusive_as_impossible(self):
        settings={}
        scene=make_advanced_scene("sports",settings)
        report=plan_original_sports_match(scene,settings,max_states=8,
                                          max_depth=1,beam_width=2)
        self.assertEqual(report["status"],"inconclusive_search_budget")
        self.assertFalse(report["independently_verified"])
        self.assertFalse(report["exhaustive_search_proved"])
        self.assertEqual(report["actions"],[])
        self.assertTrue(verify_original_sports_plan(report,scene,settings))

    def test_forged_wins_budgets_history_and_scene_fail_closed(self):
        settings,scene=self.near_goal("team")
        record=plan_original_sports_match(scene,settings,max_states=64,
                                          max_depth=4,beam_width=12)
        self.assertEqual(record["status"],"replay_verified_win")
        for change in (
            lambda x:x.update(final_home_score=999),
            lambda x:x.update(actions=["shoot","shoot"]),
            lambda x:x.update(original_replay_digest="0"*64),
            lambda x:x.update(digest="0"*64),
            lambda x:x.update(max_states=63),
        ):
            altered=deepcopy(record);change(altered)
            with self.assertRaises(SportsPlanningError):
                verify_original_sports_plan(altered,scene,settings)
        other=deepcopy(scene);other["digest"]="x"*64
        with self.assertRaises(ValueError):
            plan_original_sports_match(other,settings)

    def test_invalid_limit_types_are_rejected_without_search(self):
        settings,scene=self.near_goal("team")
        for budget in (
            {"max_states":0},{"max_states":True},{"max_states":50001},
            {"max_depth":129},{"max_depth":"32"},
            {"beam_width":0},{"beam_width":257},
        ):
            with self.assertRaises(SportsPlanningError):
                plan_original_sports_match(scene,settings,**budget)


if __name__=="__main__":
    unittest.main()
