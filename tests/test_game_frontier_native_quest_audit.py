"""Cold replays catch forged-but-rehashed RPG session states."""
import unittest
from copy import deepcopy
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError,_sha
from skeleton.jeeves.game_frontier_native_quest_audit import (
    audit_native_quest_checkpoint,verify_native_quest_checkpoint_audit,
)


class NativeQuestAuditTests(NativeQuestBatchTests):
    def test_exact_audit_of_full_and_partial_gameplay(self):
        for stop in (0,2,4):
            with self.subTest(stop=stop):
                checkpoint=self.replay(through_frame=stop,frames_per_window=2)["head_checkpoint"]
                result=audit_native_quest_checkpoint(
                    self.journal,self.pages,self.graph,self.approved,
                    checkpoint,actor_id="hero",scene_candidate_digest="d"*64,
                    frames_per_window=1)
                self.assertEqual(result["checkpoint_frame"],stop)
                self.assertEqual(result["checkpoint_digest"],checkpoint["receipt_digest"])
                self.assertEqual(result["verified_source_prefix_frames"],stop+1)
                other=audit_native_quest_checkpoint(
                    self.journal,self.pages,self.graph,self.approved,
                    checkpoint,actor_id="hero",scene_candidate_digest="d"*64,
                    frames_per_window=2)
                self.assertEqual(result,other)
                self.assertEqual(result["source_session_chain_head_digest"],
                                 checkpoint["last_session_receipt_digest"])
                self.assertTrue(verify_native_quest_checkpoint_audit(
                    self.journal,self.pages,self.graph,self.approved,checkpoint,result,
                    actor_id="hero",scene_candidate_digest="d"*64,
                    frames_per_window=1))

    def test_rehashing_forced_victory_and_flags_does_not_pass_cold_replay(self):
        checkpoint=self.replay()["head_checkpoint"]
        for variant in ("quest","flag","last_digest","cooldown","approval"):
            forged=deepcopy(checkpoint)
            if variant=="quest":
                forged["quests"]["chapter_1"]["stage"]="start"
            elif variant=="flag":
                forged["flags"]["unearned_canon_win"]=True
            elif variant=="last_digest":
                forged["last_session_receipt_digest"]="f"*64
            elif variant=="cooldown":
                forged["last_fired_ms"]["begin"]=200
            else:
                forged["approved_page_count"]=0
            forged["receipt_digest"]=_sha({
                k:v for k,v in forged.items() if k!="receipt_digest"})
            with self.subTest(variant=variant),self.assertRaises(NativeQuestSessionError):
                audit_native_quest_checkpoint(
                    self.journal,self.pages,self.graph,self.approved,forged,
                    actor_id="hero",scene_candidate_digest="d"*64)

    def test_audit_is_bound_to_original_signed_scene_actor_and_pages(self):
        checkpoint=self.replay()["head_checkpoint"]
        for kwargs in ({"scene_candidate_digest":"a"*64},{"actor_id":"npc"}):
            with self.subTest(kwargs=kwargs),self.assertRaises((NativeQuestSessionError,ValueError)):
                audit_native_quest_checkpoint(
                    self.journal,self.pages,self.graph,self.approved,
                    checkpoint,actor_id=kwargs.get("actor_id","hero"),
                    scene_candidate_digest=kwargs.get("scene_candidate_digest","d"*64))

    def test_recomputed_evidence_rejects_altered_results(self):
        checkpoint=self.replay()["head_checkpoint"]
        proven=audit_native_quest_checkpoint(
            self.journal,self.pages,self.graph,self.approved,
            checkpoint,actor_id="hero",scene_candidate_digest="d"*64)
        altered=dict(proven,approved_events_verified=10**6)
        with self.assertRaises(NativeQuestSessionError):
            verify_native_quest_checkpoint_audit(
                self.journal,self.pages,self.graph,self.approved,checkpoint,altered,
                actor_id="hero",scene_candidate_digest="d"*64)
