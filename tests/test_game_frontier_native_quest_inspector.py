"""In-world quest progress, branching choices and virtual position display."""
from copy import deepcopy
import unittest
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError
from skeleton.jeeves.game_frontier_native_quest_audit import audit_native_quest_checkpoint
from skeleton.jeeves.game_frontier_native_quest_inspector import inspect_native_quest_objectives


class NativeQuestInspectorTests(NativeQuestBatchTests):
    def snapshot(self,through):
        checkpoint=self.replay(through_frame=through)["head_checkpoint"]
        audit=audit_native_quest_checkpoint(
            self.journal,self.pages,self.graph,self.approved,checkpoint,
            actor_id="hero",scene_candidate_digest="d"*64)
        return checkpoint,audit

    def inspect(self,checkpoint,audit):
        return inspect_native_quest_objectives(
            self.journal,self.pages,self.graph,self.approved,checkpoint,audit,
            actor_id="hero",scene_candidate_digest="d"*64)

    def test_gameplay_objectives_show_source_bound_branches_and_completion(self):
        initial,proof=self.snapshot(0)
        first=self.inspect(initial,proof)
        self.assertEqual(first["quests_active"],1)
        self.assertEqual(first["quests_completed"],0)
        self.assertEqual(first["quest_entries"][0]["stage_id"],"start")
        self.assertEqual({o["stage_id"] for o in first["quest_entries"][0]["next_options"]},
                         {"middle","alternate"})
        self.assertEqual(first["quest_entries"][0]["current_objective"],"Watch the fall")
        last,proof=self.snapshot(4)
        finished=self.inspect(last,proof)
        self.assertEqual(finished["quest_entries"][0]["status"],"completed")
        self.assertEqual(finished["quests_completed"],1)
        self.assertEqual(finished["quest_entries"][0]["next_options"],[])
        self.assertEqual(finished["game_only_virtual_position_xyz_m"],
                         self.journal.native_sample(4)["actors"][0]["world_xyz_m"])
        self.assertEqual(finished["read_only_flags"],{
            "door_open":True,"quest_active":True})
        self.assertEqual(finished,self.inspect(last,proof))
        self.assertEqual(len(finished["receipt_digest"]),64)

    def test_no_approval_yields_unstarted_quest_even_after_motion(self):
        manifest=self.fixture.approval(authorized=())
        from skeleton.jeeves.game_frontier_native_quest_batch import replay_native_quest_batches
        from skeleton.jeeves.game_frontier_native_quest_audit import audit_native_quest_checkpoint
        checkpoint=replay_native_quest_batches(
            self.journal,self.pages,self.graph,manifest,actor_id="hero",
            scene_candidate_digest="d"*64)["head_checkpoint"]
        proof=audit_native_quest_checkpoint(
            self.journal,self.pages,self.graph,manifest,checkpoint,
            actor_id="hero",scene_candidate_digest="d"*64)
        display=inspect_native_quest_objectives(
            self.journal,self.pages,self.graph,manifest,checkpoint,proof,
            actor_id="hero",scene_candidate_digest="d"*64)
        self.assertEqual(display["quest_entries"][0]["status"],"not_started")
        self.assertEqual(display["quests_not_started"],1)
        self.assertEqual(display["quest_entries"][0]["next_options"],[])

    def test_forged_inspection_source_or_audit_rejected(self):
        cp,proof=self.snapshot(4)
        forged=deepcopy(proof)
        forged["approved_events_verified"]=999
        with self.assertRaises(NativeQuestSessionError):
            self.inspect(cp,forged)
        tampered=deepcopy(cp)
        tampered["flags"]["world_saved"]=True
        with self.assertRaises(NativeQuestSessionError):
            self.inspect(tampered,proof)
