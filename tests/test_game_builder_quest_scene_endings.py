"""Proof-bound original endings depend on real solved choices and shared lore."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_scene_engine import DirectorError, director_play
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.quest_director_endings import evaluate_story_ending


class OriginalEarnedEndingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = forge_director(
            "coherent_original_story", seed=517,
            regions=tuple(f"region_{i:02d}" for i in range(10)),
            quest_types=("main_story", "regional_story", "rival_story"),
            stages=3, main_goal="Keep the original world safe and free.",
        )

    def test_real_method_changes_ending_without_changing_story_goal(self):
        discovery = solve_quest(
            self.world, "quest_00", strategy="creative", authorized=True)
        mediation = solve_quest(
            self.world, "quest_00", strategy="balanced", authorized=True)
        first = evaluate_story_ending(
            self.world, discovery.replay, authorized=True)
        other = evaluate_story_ending(
            self.world, mediation.replay, authorized=True)
        self.assertEqual(first.ending, "discovery")
        self.assertEqual(other.ending, "stewardship")
        self.assertNotEqual(first.epilogue, other.epilogue)
        self.assertEqual(first.goal, other.goal)
        self.assertEqual(first.goal, self.world.bible.invariant_goal)
        self.assertEqual(first.continuity_facts, other.continuity_facts)
        self.assertEqual(len(first.continuity_facts), 3)
        self.assertEqual(first.qualifying_chapters, 3)
        self.assertTrue(first.main_quest_completed)
        self.assertNotEqual(first.digest, other.digest)

    def test_optional_victories_enrich_epilogue_without_forged_progress(self):
        regular = solve_quest(
            self.world, "quest_00", strategy="creative", authorized=True)
        optional = solve_quest(
            self.world, "quest_00", strategy="creative", optional=True,
            authorized=True,
        )
        standard = evaluate_story_ending(
            self.world, regular.replay, authorized=True)
        perfected = evaluate_story_ending(
            self.world, optional.replay, authorized=True)
        self.assertEqual(standard.ending, perfected.ending)
        self.assertEqual(perfected.optional_victories, 3)
        self.assertGreater(perfected.total_score, standard.total_score)
        self.assertIn("extraordinary care", perfected.epilogue)

    def test_desired_ending_requires_player_evidence(self):
        creative = solve_quest(
            self.world, "quest_00", strategy="creative", authorized=True)
        with self.assertRaises(DirectorError):
            evaluate_story_ending(
                self.world, creative.replay,
                desired="stewardship", authorized=True)
        with self.assertRaises(DirectorError):
            evaluate_story_ending(
                self.world, creative.replay,
                desired="independence", authorized=True)
        with self.assertRaises(PermissionError):
            evaluate_story_ending(
                self.world, creative.replay, authorized=False)
        with self.assertRaises(DirectorError):
            evaluate_story_ending(
                self.world, director_play(self.world, ()), authorized=True)

    def test_tampered_story_is_not_considered_a_valid_ending(self):
        proof = solve_quest(self.world, "quest_00", authorized=True).replay
        with self.assertRaises(DirectorError):
            evaluate_story_ending(
                self.world, replace(proof, final=replace(proof.final,
                    narrative_flags=("foreign_ending",))), authorized=True)


if __name__ == "__main__":
    unittest.main()
