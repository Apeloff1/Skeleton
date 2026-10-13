"""Reproducible multi-objective quest planning through real gameplay states."""
from __future__ import annotations

import unittest
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_scene_engine import director_play, director_verify
from skeleton.ai.game_builder.quest_pareto_planner import (
    PlannerBudget, PlannerError, find_quest_routes,
)


class ParetoQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "pareto_routes",seed=5574,
            regions=tuple(f"zone_{i:02d}" for i in range(8)),
            quest_types=("main_story","investigation","escort_path"),
            stages=2,placement="story",
            main_goal="Secure the original new world without erasing local cultures.",
        )

    def test_multiple_real_chapter_routes_and_proof_independently_replay(self):
        search=find_quest_routes(
            self.world,"quest_00",objective="balanced",
            budget=PlannerBudget(max_expansions=600,beam=16,max_actions=70),
            authorized=True,
        )
        self.assertGreater(search.expanded_states,2)
        self.assertGreaterEqual(search.completed_candidates,2)
        self.assertGreaterEqual(len(search.methods_explored),2)
        self.assertEqual(search.routes[0].state.world_digest,self.world.digest)
        self.assertEqual(len(search.routes[0].method_sequence),2)
        self.assertTrue(all("quest_00" in r.state.complete for r in search.routes))
        for route in search.routes:
            replay=director_play(self.world,route.actions)
            director_verify(self.world,replay)
            self.assertEqual(replay.final,route.state)
            self.assertEqual(route.certified_replay_digest,replay.digest)
            self.assertEqual(route.elapsed,replay.final.turn)

    def test_speed_creativity_and_optional_scores_are_distinct(self):
        options={}
        for preference in ("speed","creative","thorough","balanced"):
            options[preference]=find_quest_routes(
                self.world,"quest_00",objective=preference,
                budget=PlannerBudget(max_expansions=700,beam=20,max_actions=75),
                authorized=True,
            )
        fast=options["speed"].routes[0]
        creative=options["creative"].routes[0]
        thorough=options["thorough"].routes[0]
        self.assertLessEqual(fast.elapsed,creative.elapsed)
        self.assertGreaterEqual(creative.creative_count,fast.creative_count)
        self.assertGreaterEqual(thorough.optional_count,fast.optional_count)
        self.assertGreater(thorough.score,0)
        # Legacy Python director miscalculates later-stage speed, so the
        # planner explicitly tracks clock parity rather than hiding it.
        self.assertTrue(all(type(route.legacy_score_mismatch) is bool
                            for route in options["balanced"].routes))

    def test_search_is_deterministic_and_hardware_bounded(self):
        budget=PlannerBudget(max_expansions=550,beam=12,max_actions=70)
        first=find_quest_routes(self.world,"quest_00",
                                budget=budget,authorized=True)
        second=find_quest_routes(self.world,"quest_00",
                                 budget=budget,authorized=True)
        self.assertEqual(first.digest,second.digest)
        self.assertLessEqual(first.expanded_states,
                             budget.max_expansions*len(self.world.quests[0].stages)*
                             budget.beam)
        self.assertFalse(first.payload()["native_engine_convergence_claimed"])

    def test_rejects_cross_quest_shortcuts_and_invented_plans(self):
        with self.assertRaises(PermissionError):
            find_quest_routes(self.world,"quest_00",authorized=False)
        with self.assertRaises(PlannerError):
            find_quest_routes(self.world,"fake_quest",authorized=True)
        with self.assertRaises(PlannerError):
            find_quest_routes(self.world,"quest_00",objective="plagiarism",
                              authorized=True)
        with self.assertRaises(PlannerError):
            PlannerBudget(max_expansions=1)
        with self.assertRaises(PlannerError):
            PlannerBudget(max_actions=2048)


if __name__=="__main__":
    unittest.main()
