"""Grounded personas, adversarial game test family coverage and knowledge signals."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.game_tester_almanac import (
    PlaytestError,TEST_FAMILIES,TESTER_PERSONAS,test_game_personas,
)


class GameTesterAlmanacTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "playtester_garden",seed=72612,
            regions=tuple(f"district_{i:02d}" for i in range(8)),
            quest_types=("main_story","investigation","rival_story"),
            stages=3,placement="story",
            main_goal="Keep the original living world free of outside influence.",
        )

    def test_five_independent_playtest_personas_execute_real_world_and_24_attacks(self):
        almanac=test_game_personas(self.world,"quest_00",authorized=True)
        self.assertTrue(almanac.passed)
        self.assertEqual(len(TEST_FAMILIES),24)
        self.assertEqual(len(TESTER_PERSONAS),5)
        self.assertEqual(len(almanac.testers),5)
        self.assertEqual(len(almanac.probes),5*24)
        self.assertTrue(all(p.detected for p in almanac.probes))
        self.assertEqual({p.family for p in almanac.probes},set(TEST_FAMILIES))
        self.assertEqual(len({t.replay_digest for t in almanac.testers})>=3,True)
        self.assertEqual({t.source_story_goal for t in almanac.testers},
                         {self.world.bible.invariant_goal})
        self.assertEqual({t.completed_stages for t in almanac.testers},{3})
        self.assertGreater(almanac.visited_scene_count,1)
        self.assertTrue(any(t.optional_awards>0 for t in almanac.testers))
        self.assertTrue(all(t.mission_parity for t in almanac.testers))
        self.assertFalse(almanac.payload()["human_playtest_approval"])
        self.assertFalse(almanac.payload()["neural_network_trained"])

    def test_trainable_observations_are_replayable_not_random_or_fabricated(self):
        a=test_game_personas(self.world,"quest_00",authorized=True,
                             max_personas=3,mutation_families=TEST_FAMILIES[:8])
        b=test_game_personas(self.world,"quest_00",authorized=True,
                             max_personas=3,mutation_families=TEST_FAMILIES[:8])
        self.assertEqual(a.digest,b.digest)
        self.assertEqual(a.payload()["adversarial_attempts"],24)
        self.assertTrue(a.passed)
        self.assertGreater(a.unique_solution_patterns,1)

    def test_testers_refuse_fabricated_family_or_insufficient_real_quest(self):
        with self.assertRaises(PlaytestError):
            test_game_personas(self.world,"phantom",authorized=True)
        with self.assertRaises(PermissionError):
            test_game_personas(self.world,"quest_00",authorized=False)
        with self.assertRaises(PlaytestError):
            test_game_personas(self.world,"quest_00",authorized=True,
                               mutation_families=("fake_external_model",))
        with self.assertRaises(PlaytestError):
            test_game_personas(self.world,"quest_00",authorized=True,
                               max_personas=1)


if __name__=="__main__":
    unittest.main()
