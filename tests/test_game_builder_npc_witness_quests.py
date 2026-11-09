"""Independent replay-backed NPC witness and emergent story opportunities."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.npc_witness_quest_engine import (
    WitnessError,observe_story,validate_witness,
)
from skeleton.ai.game_builder.quest_scene_engine import DirectorAction, director_play


class NPCWitnessStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "npc_witness_story",seed=104772,
            regions=tuple(f"realm_{i:02d}" for i in range(8)),
            quest_types=("main_story","combat","investigation","profession"),
            stages=3,placement="story",
            main_goal="Preserve the original realm and its free communities.",
        )
        cls.proof=solve_quest(cls.world,"quest_00",authorized=True).replay

    def test_witnesses_create_original_motive_grounded_story_opportunities(self):
        campaign=observe_story(self.world,self.proof,population=64,
                               active_budget=28,ambient_budget=28,
                               authorized=True)
        self.assertTrue(campaign.witnessed)
        self.assertTrue(campaign.opportunities)
        self.assertEqual(campaign.world_digest,self.world.digest)
        self.assertEqual(campaign.original_replay_digest,self.proof.digest)
        for witness in campaign.witnessed:
            validate_witness(self.world,self.proof,witness,authorized=True)
            self.assertEqual(witness.world_digest,self.world.digest)
            self.assertEqual(len(witness.source_memory_digest),64)
        for quest in campaign.opportunities:
            self.assertEqual(quest.story_goal,self.world.bible.invariant_goal)
            self.assertEqual(len(quest.chapters),2)
            self.assertEqual(quest.status,"proposed_review_required")
            self.assertTrue(all(len(stage.allowed_scenes)>0
                                for stage in quest.chapters))
            self.assertTrue(all(stage.victory.op=="any" for stage in quest.chapters))
            self.assertFalse(quest.payload()["review_approved"])
        other=observe_story(self.world,self.proof,population=64,
                             active_budget=28,ambient_budget=28,
                             authorized=True)
        self.assertEqual(campaign.digest,other.digest)

    def test_telepathic_observer_or_forged_action_is_rejected(self):
        witness=observe_story(self.world,self.proof,population=40,
                              authorized=True).witnessed[0]
        with self.assertRaises(WitnessError):
            validate_witness(self.world,self.proof,
                             replace(witness,scene="scene_07"),authorized=True)
        with self.assertRaises(WitnessError):
            validate_witness(self.world,self.proof,
                             replace(witness,action_digest="0"*64),authorized=True)
        with self.assertRaises(WitnessError):
            validate_witness(self.world,self.proof,
                             replace(witness,action_index=10000),authorized=True)
        with self.assertRaises(PermissionError):
            validate_witness(self.world,self.proof,witness,authorized=False)

    def test_unobserved_world_cannot_unlock_quest(self):
        # Travel and waiting are not witnessed narrative incidents.
        proof=director_play(self.world,(
            DirectorAction("wait","wait","scene_00"),
        ))
        campaign=observe_story(self.world,proof,population=24,
                               authorized=True)
        self.assertEqual(campaign.witnessed,())
        self.assertEqual(campaign.opportunities,())
        self.assertEqual(campaign.unrepresented_actions,1)

    def test_attestations_do_not_automatically_publish_or_train_ai(self):
        campaign=observe_story(self.world,self.proof,population=24,
                               maximum_witnesses=8,authorized=True)
        self.assertLessEqual(len(campaign.witnessed),8)
        self.assertFalse(campaign.payload()["automatic_npc_training"])
        self.assertTrue(campaign.payload()["human_author_review_required"])
        with self.assertRaises(PermissionError):
            observe_story(self.world,self.proof,authorized=False)
        with self.assertRaises(WitnessError):
            observe_story(self.world,self.proof,population=1000,
                          authorized=True)


if __name__=="__main__":
    unittest.main()
