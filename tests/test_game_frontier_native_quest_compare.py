"""Verified alternative RPG approvals produce explainable diverging branches."""
import unittest
from copy import deepcopy
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_quest_batch import replay_native_quest_batches
from skeleton.jeeves.game_frontier_native_quest_compare import compare_native_quest_outcomes
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError


class NativeQuestComparisonTests(NativeQuestBatchTests):
    def checkpoint(self,manifest):
        return replay_native_quest_batches(
            self.journal,self.pages,self.graph,manifest,actor_id="hero",
            scene_candidate_digest="d"*64)["head_checkpoint"]

    def compare(self,left,right,lc,rc):
        return compare_native_quest_outcomes(
            self.journal,self.journal,self.pages,self.graph,
            left,right,lc,rc,actor_id="hero",scene_candidate_digest="d"*64)

    def test_same_approval_has_equal_state_and_source(self):
        left=self.checkpoint(self.approved)
        result=self.compare(self.approved,self.approved,left,deepcopy(left))
        self.assertEqual(result["changed_quests"],[])
        self.assertEqual(result["changed_flags"],[])
        self.assertTrue(result["identical_quest_state"])
        self.assertTrue(result["native_frame_digest_equal"])
        self.assertEqual(result["approved_only_on_left"],[])

    def test_fork_outcomes_show_quest_flags_and_approved_receipts(self):
        zero=self.fixture.approval(authorized=())
        left=self.checkpoint(self.approved)
        right=self.checkpoint(zero)
        report=self.compare(self.approved,zero,left,right)
        self.assertFalse(report["identical_quest_state"])
        self.assertTrue(report["native_frame_digest_equal"])
        self.assertEqual([row["id"] for row in report["changed_quests"]],
                         ["chapter_1"])
        self.assertEqual({row["id"] for row in report["changed_flags"]},
                         {"quest_active","door_open"})
        self.assertEqual(len(report["approved_only_on_left"]),3)
        self.assertEqual(len(report["approved_only_on_right"]),0)
        self.assertEqual(len(report["receipt_digest"]),64)
        self.assertEqual(report,self.compare(self.approved,zero,left,right))

    def test_source_forgery_and_different_time_are_not_comparable(self):
        other=self.fixture.approval(authorized=())
        left=self.checkpoint(self.approved)
        right=self.checkpoint(other)
        altered=deepcopy(right)
        altered["flags"]["faked"]=True
        with self.assertRaises(NativeQuestSessionError):
            self.compare(self.approved,other,left,altered)
        altered=deepcopy(right)
        altered["frame"]=1
        with self.assertRaises(NativeQuestSessionError):
            self.compare(self.approved,other,left,altered)
