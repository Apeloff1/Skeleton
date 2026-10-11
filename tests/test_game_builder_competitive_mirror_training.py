"""Adversarial original NPC witness quest attacks become safe training candidates."""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.npc_witness_quest_engine import (
    WitnessError, observe_story, audit_witness_campaign,
)
from skeleton.ai.game_builder.competitive_mirror_training import (
    MirrorCompetitionError, ATTACK_FAMILIES,
    run_mirror_competition, distill_mirror_cases, training_jsonl,
    split_project, TrainingCandidate,
)


class CompetitiveWitnessMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "competitive_original",seed=7127,
            regions=tuple(f"place_{i:02d}" for i in range(8)),
            quest_types=("main_story","research","investigation")
            if False else ("main_story","investigation","regional_story"),
            stages=2,
        )
        cls.replay=solve_quest(cls.world,"quest_00",authorized=True).replay
        cls.campaign=observe_story(
            cls.world,cls.replay,population=24,
            active_budget=12,ambient_budget=12,maximum_witnesses=16,
            authorized=True,
        )

    def test_real_18_family_red_team_blue_team_and_critic(self):
        report=run_mirror_competition(
            self.world,self.replay,self.campaign,
            population=24,active_budget=12,ambient_budget=12,
            maximum_witnesses=16,attempts=36,authorized=True,
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.payload()["attack_family_count"],18)
        self.assertEqual(report.payload()["detected"],36)
        self.assertEqual(report.payload()["missed"],0)
        self.assertEqual({p.family for p in report.probes},set(ATTACK_FAMILIES))
        self.assertTrue(report.control_passed)
        self.assertTrue(report.reviewer_agreement)
        self.assertEqual(report.digest,run_mirror_competition(
            self.world,self.replay,self.campaign,
            population=24,active_budget=12,ambient_budget=12,
            maximum_witnesses=16,attempts=36,authorized=True,
        ).digest)

    def test_witness_evidence_cannot_be_rewritten_in_finished_review(self):
        audit_witness_campaign(self.world,self.replay,self.campaign,
            population=24,active_budget=12,ambient_budget=12,
            maximum_witnesses=16,authorized=True)
        bad=replace(self.campaign,storyboard_goal="Fictional disallowed goal")
        with self.assertRaises(WitnessError):
            audit_witness_campaign(self.world,self.replay,bad,
                population=24,active_budget=12,ambient_budget=12,
                maximum_witnesses=16,authorized=True)
        missing=replace(self.campaign,witnessed=())
        with self.assertRaises(WitnessError):
            audit_witness_campaign(self.world,self.replay,missing,
                population=24,active_budget=12,ambient_budget=12,
                maximum_witnesses=16,authorized=True)

    def test_training_examples_are_quarantined_project_grouped_and_reproducible(self):
        report=run_mirror_competition(
            self.world,self.replay,self.campaign,
            population=24,active_budget=12,ambient_budget=12,
            maximum_witnesses=16,attempts=36,authorized=True,
        )
        candidates=distill_mirror_cases(report,self.campaign,authorized=True)
        self.assertEqual(len(candidates),36)
        self.assertEqual(len({x.example_id for x in candidates}),36)
        self.assertEqual({x.split for x in candidates},
                         {split_project(self.world.digest)})
        self.assertEqual({x.approval for x in candidates},{"quarantined"})
        self.assertEqual({x.expected["decision"] for x in candidates},{"reject"})
        jsonl=training_jsonl(candidates,authorized=True)
        entries=[json.loads(line) for line in jsonl.decode().splitlines()]
        self.assertEqual(len(entries),36)
        self.assertTrue(all(e["approval"]=="quarantined" for e in entries))
        self.assertEqual(jsonl,training_jsonl(candidates,authorized=True))
        with self.assertRaises(MirrorCompetitionError):
            training_jsonl((replace(candidates[0],approval="approved"),),
                           authorized=True)

    def test_no_unreviewed_mirror_claim_or_implicit_schedule_change(self):
        with self.assertRaises(PermissionError):
            run_mirror_competition(
                self.world,self.replay,self.campaign,
                population=24,authorized=False)
        with self.assertRaises(MirrorCompetitionError):
            run_mirror_competition(
                self.world,self.replay,self.campaign,
                population=24,attempts=1,authorized=True)


if __name__=="__main__":
    unittest.main()
