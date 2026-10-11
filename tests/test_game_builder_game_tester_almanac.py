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

    def test_gameplay_almanac_produces_actual_before_after_training_curriculum(self):
        from skeleton.ai.game_builder.game_learning_almanac import (
            build_game_tester_curriculum,
        )
        report=test_game_personas(self.world,"quest_00",
                                  max_personas=3,
                                  mutation_families=TEST_FAMILIES[:10],
                                  authorized=True)
        curriculum=build_game_tester_curriculum(report,authorized=True)
        self.assertEqual(len(curriculum.examples),33)
        self.assertEqual(curriculum.red_team_count,30)
        self.assertEqual(curriculum.positive_controls,3)
        first=curriculum.examples[0]
        self.assertEqual(first.expected["decision"],"reject")
        self.assertIn("before",first.input)
        self.assertIn("after",first.input)
        self.assertNotEqual(first.input["before"],first.input["after"])
        self.assertEqual(first.evidence["game_tester_digest"],report.digest)
        self.assertEqual(curriculum.examples[-1].expected["decision"],
                         "accept_witnessed_incident_only")
        with self.assertRaises(PermissionError):
            build_game_tester_curriculum(report,authorized=False)

    def test_gameplay_cli_creates_replay_almanac_and_quarantined_cases(self):
        import io,json,tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
        from skeleton.ai.game_builder.game_workspace_cli import main as studio_cli
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"world.json"
            source.write_text(json.dumps(self.world.payload()),encoding="utf-8")
            studio=GameWorkspace.create(Path(folder)/"studio",authorized=True)
            output=io.StringIO()
            with redirect_stdout(output):
                code=studio_cli([
                    "playtest-game","--root",str(studio.root),
                    "--director-blueprint",str(source),
                    "--testers","3","--attack-families","8",
                    "--quarantine-learning","--trusted-local-operator",
                ])
            self.assertEqual(code,0)
            result=json.loads(output.getvalue())
            self.assertEqual(result["report"]["tester_count"],3)
            self.assertEqual(result["report"]["adversarial_attempts"],24)
            self.assertEqual(result["candidate_examples"],27)
            self.assertFalse(result["model_training_executed"])
            self.assertIsNotNone(result["quarantined"])
            self.assertEqual(studio.tree()["training_quarantine"],1)

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
