"""Companion builds diverse, verified games and evidence-based almanac entries."""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from skeleton.ai.game_builder.companion_curriculum import (
    CompanionCurriculumError, plan_original_companion_intents,
    measure_original_practice, validate_practice_cohort,
)
from skeleton.ai.game_builder.original_game_studio import run_original_game_studio
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_simulation import play_actions
from skeleton.ai.game_builder.playable_world import GameBuildIntent


class OriginalCompanionCurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = GameBuildIntent(
            project_id="original-companion-mechanical-curriculum",
            title="Original Living Practice",
            subtitle="Create whole new playable games for separate challenge levels.",
            seed=872109, width=11, height=11, levels=1,
            collectibles_per_level=2, hazards_per_level=3,
            theme="space", starting_health=4,
        )

    def test_mechanically_diverse_original_games_with_independent_winning_replays(self):
        intents = plan_original_companion_intents(self.base, 8)
        self.assertEqual(intents, plan_original_companion_intents(self.base, 8))
        self.assertEqual(len(intents), 8)
        self.assertEqual(len(set(i.project_id for i in intents)), 8)
        self.assertEqual(len(set(i.seed for i in intents)), 8)
        self.assertGreater(len({i.theme for i in intents}), 3)
        self.assertGreater(len({i.width for i in intents}), 1)
        self.assertGreater(len({i.height for i in intents}), 1)
        self.assertGreater(len({i.levels for i in intents}), 1)
        self.assertGreater(len({i.collectibles_per_level for i in intents}), 1)
        self.assertGreater(len({i.hazards_per_level for i in intents}), 1)
        diversity = validate_practice_cohort(intents, parent=self.base)
        self.assertGreaterEqual(diversity, 4)
        measures = []
        for item in intents:
            compiled = compile_original_game(item, authorized=True)
            insight = measure_original_practice(
                compiled.world, compiled.proof,
                authorized=True, distinct_themes=diversity,
            )
            self.assertEqual(insight.safe_solution_turns,
                             compiled.proof.final_state.steps)
            self.assertEqual(insight.world_digest, compiled.world.digest)
            self.assertEqual(insight.proof_digest, compiled.proof.digest)
            self.assertGreater(insight.challenge_score, 0)
            self.assertGreater(insight.verified_experience, 0)
            self.assertTrue(insight.observation.endswith("No human player was tested."))
            self.assertFalse(insight.to_payload()["learned_model_weights"])
            self.assertEqual(insight.digest, measure_original_practice(
                compiled.world, compiled.proof,
                authorized=True, distinct_themes=diversity).digest)
            measures.append(insight)
        self.assertGreater(len(set(x.challenge_score for x in measures)), 2)

    def test_studio_exports_real_companion_almanac_and_practice_bundle_evidence(self):
        studio = run_original_game_studio(
            self.base, authorized=True,
            companion_practice_games=5, mirror_attempts=64,
        )
        self.assertEqual(len(studio.practice), 5)
        almanac = json.loads(studio.package.files["studio/companion_almanac.json"])
        self.assertEqual(len(almanac["insights"]), 5)
        self.assertEqual(len({g["world_digest"] for g in almanac["insights"]}), 5)
        self.assertGreater(almanac["unique_themes"], 2)
        self.assertEqual(sum(i.capability_xp for i in studio.practice),
                         sum(g["verified_experience"] for g in almanac["insights"]))
        for practice, observation in zip(studio.practice, almanac["insights"]):
            self.assertEqual(practice.insight_digest,
                             measure_digest(observation))
            self.assertEqual(practice.challenge_score,
                             observation["challenge_score"])
            self.assertEqual(practice.winning_steps,
                             observation["safe_solution_turns"])
            nested = json.loads(
                studio.package.files[practice.package_path + "/release.json"])
            self.assertEqual(nested["world_digest"], observation["world_digest"])
            self.assertEqual(nested["proof_digest"], observation["proof_digest"])
        receipt = json.loads(studio.package.files["studio/executed_tool_receipts.json"])
        self.assertEqual(len(receipt["practice_insight_digests"]), 5)
        self.assertEqual(
            receipt["practice_insight_digests"],
            [i.insight_digest for i in studio.practice],
        )

    def test_fail_closed_on_no_win_replay_or_invalid_curriculum(self):
        item = plan_original_companion_intents(self.base, 1)[0]
        game = compile_original_game(item, authorized=True)
        unfinished = play_actions(game.world, (), authorized=True)
        with self.assertRaisesRegex(CompanionCurriculumError, "winning"):
            measure_original_practice(
                game.world, unfinished, authorized=True)
        with self.assertRaises(PermissionError):
            measure_original_practice(
                game.world, game.proof, authorized=False)
        with self.assertRaises(CompanionCurriculumError):
            plan_original_companion_intents(self.base, 9)
        with self.assertRaises(CompanionCurriculumError):
            plan_original_companion_intents(self.base, True)
        with self.assertRaises(CompanionCurriculumError):
            validate_practice_cohort((item, item), parent=self.base)
        with self.assertRaises(CompanionCurriculumError):
            measure_original_practice(
                game.world, game.proof, authorized=True, distinct_themes=0)

    def test_max_length_identity_and_resource_bounds(self):
        base = replace(
            self.base, project_id="A" + "x" * 127,
            width=41, height=41, levels=8,
            collectibles_per_level=6, hazards_per_level=24,
        )
        cohort = plan_original_companion_intents(base, 8)
        self.assertEqual(len(cohort), 8)
        self.assertTrue(all(len(i.project_id) <= 128 for i in cohort))
        self.assertTrue(all(i.width == 41 and i.height == 41
                            and i.levels <= 8 and i.hazards_per_level <= 24
                            for i in cohort))


def measure_digest(data):
    from skeleton.ai.game_builder.contracts import canonical_digest
    return canonical_digest(data)


if __name__ == "__main__":
    unittest.main()
