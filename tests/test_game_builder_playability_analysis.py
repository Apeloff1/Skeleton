"""Action-by-action verified playtest analytics, advisory UX feedback and cohorts."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.playable_simulation import (
    GameReplay, GameplayError, demonstrate_solvable, play_actions,
)
from skeleton.ai.game_builder.playability_analysis import (
    PlayabilityAnalysisError, analyze_replay, aggregate_playability,
)


def make_world(seed=12):
    return generate_playable_world(
        GameBuildIntent(
            project_id="playability-project", title="Original Circuit Maze",
            subtitle="Collect all crystals in an accessible original maze.",
            seed=seed, width=19, height=15, levels=2,
            collectibles_per_level=3, hazards_per_level=6,
            theme="arcade", starting_health=3,
        ), authorized=True,
    )


class GameExperienceTests(unittest.TestCase):
    def setUp(self):
        self.world = make_world()
        self.proof = demonstrate_solvable(self.world, authorized=True)

    def test_winning_game_has_grounded_level_metrics(self):
        report = analyze_replay(self.world, self.proof, authorized=True)
        self.assertTrue(report.completed_game)
        self.assertEqual(len(report.levels), 2)
        self.assertEqual(sum(level.collectibles_found for level in report.levels), 6)
        self.assertEqual(sum(level.moves for level in report.levels),
                         len(self.proof.action_receipts))
        self.assertTrue(all(level.completed for level in report.levels))
        self.assertTrue(all(level.route_overrun_ppm is not None for level in report.levels))
        self.assertEqual(report.world_digest, self.world.digest)
        self.assertEqual(report.replay_digest, self.proof.digest)
        self.assertTrue(report.to_payload()["requires_human_evaluation"])
        self.assertTrue(report.to_payload()["improvement_proposals_are_nonexecuting"])
        self.assertEqual(len(report.to_payload()["report_digest"]), 64)

    def test_wall_contacts_trigger_specific_actionable_advice(self):
        trace = play_actions(self.world, ("up",) * 20, authorized=True)
        report = analyze_replay(self.world, trace, authorized=True)
        level = report.levels[0]
        self.assertEqual(level.wall_contacts, 20)
        self.assertEqual(level.wall_friction_ppm, 1_000_000)
        self.assertEqual(level.unique_tiles_visited, 1)
        self.assertFalse(report.completed_game)
        self.assertIn("wall_friction", {finding.signal for finding in report.findings})
        # Repeatedly walking into the same wall proves navigation friction;
        # it is insufficient evidence that the objectives themselves are
        # defective. Do not infer a gameplay defect from player inactivity.
        self.assertNotIn("incomplete_objectives", {finding.signal for finding in report.findings})
        self.assertTrue(all(len(finding.evidence_digest) == 64 for finding in report.findings))

    def test_short_incomplete_game_does_not_overclaim_defects(self):
        trace = play_actions(self.world, (), authorized=True)
        report = analyze_replay(self.world, trace, authorized=True)
        self.assertFalse(report.completed_game)
        self.assertEqual(report.levels[0].moves, 0)
        self.assertEqual(report.findings, ())
        self.assertIsNone(report.levels[0].route_overrun_ppm)

    def test_revisited_path_is_measured_without_personality_inference(self):
        trace = play_actions(
            self.world, ("up", "left", "right", "left", "right") * 6,
            authorized=True,
        )
        report = analyze_replay(self.world, trace, authorized=True)
        self.assertTrue(report.no_preference_inference)
        self.assertEqual(len(report.levels), 1)
        self.assertGreaterEqual(report.levels[0].wall_contacts, 1)
        self.assertGreaterEqual(report.levels[0].moves, 30)
        self.assertEqual(report.levels[0].hazard_hits, 0)

    def test_rejects_tampered_action_receipts(self):
        fake = replace(
            self.proof,
            action_receipts=(
                replace(self.proof.action_receipts[0], before_digest="0" * 64),
            ) + self.proof.action_receipts[1:],
        )
        with self.assertRaises(GameplayError):
            analyze_replay(self.world, fake, authorized=True)

    def test_rejects_crossworld_replay(self):
        with self.assertRaises(GameplayError):
            analyze_replay(make_world(999), self.proof, authorized=True)

    def test_authorization_required(self):
        with self.assertRaises(PermissionError):
            analyze_replay(self.world, self.proof, authorized=False)

    def test_cohort_uses_distinct_real_replays(self):
        base = self.world.levels[0].safe_solution
        one = play_actions(self.world, base[:5], authorized=True)
        two = play_actions(self.world, base[:6], authorized=True)
        three = self.proof
        cohort = aggregate_playability(
            self.world, (one, two, three),
            consent_to_aggregate=True, authorized=True,
        )
        data = cohort.to_payload()
        self.assertEqual(data["sample_count"], 3)
        self.assertEqual(data["completed_count"], 1)
        self.assertEqual(data["completion_rate_ppm"], 333333)
        self.assertEqual(data["world_digest"], self.world.digest)
        self.assertTrue(data["requires_independent_playtest_review"])
        self.assertEqual(len(data["cohort_digest"]), 64)
        self.assertEqual(len(cohort.report_digests), 3)

    def test_cohort_rejects_duplicate_trace_inflation(self):
        with self.assertRaisesRegex(PlayabilityAnalysisError, "duplicate"):
            aggregate_playability(
                self.world, (self.proof, self.proof, self.proof),
                consent_to_aggregate=True, authorized=True,
            )

    def test_cohort_rejects_unapproved_aggregation(self):
        trace = play_actions(self.world, ("up",), authorized=True)
        with self.assertRaisesRegex(PlayabilityAnalysisError, "consent"):
            aggregate_playability(
                self.world, (self.proof, trace, self.proof),
                consent_to_aggregate=False, authorized=True,
            )
        with self.assertRaises(PermissionError):
            aggregate_playability(
                self.world, (self.proof, trace, self.proof),
                consent_to_aggregate=True, authorized=False,
            )

    def test_cohort_rejects_crossworld_and_wrong_type(self):
        other = demonstrate_solvable(make_world(999), authorized=True)
        with self.assertRaises(GameplayError):
            aggregate_playability(
                self.world, (self.proof, other, play_actions(self.world, ("up",), authorized=True)),
                consent_to_aggregate=True, authorized=True,
            )
        with self.assertRaises(PlayabilityAnalysisError):
            aggregate_playability(
                self.world, (self.proof, "not-replay", other),
                consent_to_aggregate=True, authorized=True,
            )

    def test_deterministic_report_for_identical_actions(self):
        actions = self.world.levels[0].safe_solution[:20]
        first = analyze_replay(self.world, play_actions(self.world, actions, authorized=True),
                               authorized=True)
        second = analyze_replay(self.world, play_actions(self.world, actions, authorized=True),
                                authorized=True)
        self.assertEqual(first, second)
        self.assertEqual(first.to_payload(), second.to_payload())

    def test_longer_than_one_world_reports_each_reached_level(self):
        report = analyze_replay(self.world, self.proof, authorized=True)
        self.assertEqual([level.level_index for level in report.levels], [0, 1])
        self.assertEqual(
            [level.collectibles_found for level in report.levels], [3, 3],
        )


if __name__ == "__main__":
    unittest.main()
