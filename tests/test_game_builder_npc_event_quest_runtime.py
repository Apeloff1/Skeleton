"""NPC eyewitness incidents causally activate real independently replayed missions."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.npc_witness_quest_engine import observe_story
from skeleton.ai.game_builder.npc_event_quest_runtime import (
    WitnessProgressError,replay_witness_quests,
)
from skeleton.ai.game_builder.modular_mission_runtime import (
    ObjectiveStage,Formula,atom,
)


class EmergentNPCQuestRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "living_incidents",seed=5111,
            regions=tuple(f"district_{i:02d}" for i in range(8)),
            quest_types=("main_story","investigation","regional_story"),
            stages=3,placement="story",
        )
        cls.replay=solve_quest(
            cls.world,"quest_00",strategy="ordinary",authorized=True,
        ).replay
        cls.campaign=observe_story(
            cls.world,cls.replay,population=24,
            active_budget=12,ambient_budget=12,
            maximum_witnesses=24,authorized=True,
        )

    def test_original_witness_opportunities_replay_without_time_travel(self):
        self.assertGreater(len(self.campaign.opportunities),0)
        replay=replay_witness_quests(
            self.world,self.replay,self.campaign,population=24,
            active_budget=12,ambient_budget=12,
            maximum_witnesses=24,authorized=True,
        )
        self.assertEqual(replay.world_digest,self.world.digest)
        self.assertEqual(len(replay.quests),len(self.campaign.opportunities))
        for record in replay.quests:
            self.assertIn(record.status,{"active","solved"})
            self.assertLessEqual(record.stage_index,record.stage_count)
            for result in record.results:
                self.assertGreater(result.completed_at_action,
                                   result.activated_at_action-1)
                self.assertGreater(result.reward,0)
        self.assertTrue(replay.payload()["review_required_before_canonical_inclusion"])
        self.assertFalse(replay.payload()["real_native_integration_verified"])
        self.assertEqual(replay.digest,replay_witness_quests(
            self.world,self.replay,self.campaign,population=24,
            active_budget=12,ambient_budget=12,
            maximum_witnesses=24,authorized=True).digest)

    def test_designer_can_make_witness_triggered_two_chapter_original_quest_really_solvable(self):
        q=next(q for q in self.campaign.opportunities
               if q.witness.action_kind=="research"
               and q.witness.action_target=="objective_00_00")
        # These follow the *subsequent* authored scenes and actually execute.
        # Both chapters have multiple acceptable solutions.
        chapters=(
            ObjectiveStage(
                "relief_01","Investigate consequences before moving on.",
                Formula("any",children=(
                    atom("research","objective_00_01",location="scene_01"),
                    atom("inspect","insight_00_01",location="scene_01"),
                )),
                (),("scene_01",),deadline=24,reward=120,
                consequence="heard_investigators",
            ),
            ObjectiveStage(
                "relief_02","Restore trust while preserving the shared goal.",
                Formula("any",children=(
                    atom("research","objective_00_02",location="scene_02"),
                    atom("inspect","insight_00_02",location="scene_02"),
                )),
                (),("scene_02",),deadline=24,reward=130,
                consequence="restored_public_trust",
            ),
        )
        replay=replay_witness_quests(
            self.world,self.replay,self.campaign,population=24,
            active_budget=12,ambient_budget=12,
            maximum_witnesses=24,authored_chapters={q.key:chapters},
            human_reviewed=True,authorized=True,
        )
        completed=next(x for x in replay.quests if x.key==q.key)
        self.assertEqual(completed.status,"solved")
        self.assertEqual(completed.stage_index,2)
        self.assertEqual(len(completed.results),2)
        self.assertGreater(completed.results[0].completed_at_action,
                           q.witness.action_index)
        self.assertGreater(completed.results[1].completed_at_action,
                           completed.results[0].completed_at_action)
        self.assertIsNotNone(replay.reviewed_source_digest)
        self.assertGreater(completed.completion_turn,q.witness.observed_turn)

    def test_historical_events_cannot_retrospectively_finish_a_new_quest(self):
        q=next(q for q in self.campaign.opportunities
               if q.witness.action_kind=="research"
               and q.witness.action_target=="objective_00_00")
        old=(
            ObjectiveStage(
                "retro_00","Reject impossible pre-trigger completion.",
                Formula("any",children=(
                    atom("research","objective_00_00",location="scene_00"),
                    atom("inspect","insight_00_00",location="scene_00"),
                )),
                (),("scene_00",),
            ),
            ObjectiveStage(
                "retro_01","Do not unlock until the prior actual requirement.",
                Formula("any",children=(
                    atom("research","objective_00_01",location="scene_01"),
                    atom("inspect","insight_00_01",location="scene_01"),
                )),
                (),("scene_01",),
            ),
        )
        result=replay_witness_quests(
            self.world,self.replay,self.campaign,population=24,
            active_budget=12,ambient_budget=12,
            maximum_witnesses=24,
            authored_chapters={q.key:old},
            human_reviewed=True,authorized=True,
        )
        entry=next(x for x in result.quests if x.key==q.key)
        self.assertEqual(entry.status,"active")
        self.assertEqual(entry.stage_index,0)

    def test_rejects_fake_mission_objectives_and_unreviewed_rewrites(self):
        q=self.campaign.opportunities[0]
        stage=ObjectiveStage(
            "unreachable","An invented requirement must never become a quest.",
            Formula("any",children=(
                atom("research","made_up_target"),
                atom("inspect","made_up_evidence"),
            )),(),("scene_00",),
        )
        with self.assertRaises(WitnessProgressError):
            replay_witness_quests(
                self.world,self.replay,self.campaign,population=24,
                active_budget=12,ambient_budget=12,
                maximum_witnesses=24,
                authored_chapters={q.key:(stage,stage)},
                human_reviewed=True,authorized=True,
            )
        with self.assertRaises(WitnessProgressError):
            replay_witness_quests(
                self.world,self.replay,self.campaign,population=24,
                active_budget=12,ambient_budget=12,
                maximum_witnesses=24,
                authored_chapters={q.key:q.chapters},
                human_reviewed=False,authorized=True,
            )
        with self.assertRaises(PermissionError):
            replay_witness_quests(
                self.world,self.replay,self.campaign,population=24,
                authorized=False,
            )


if __name__=="__main__":
    unittest.main()
