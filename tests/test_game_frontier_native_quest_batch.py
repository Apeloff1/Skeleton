"""Multi-window native game session batches against existing canonical replay."""
from copy import deepcopy
import unittest
from tests.test_game_frontier_native_quest_session import (
    NativeQuestSessionTests,page_source,graph,
)
from skeleton.jeeves.game_frontier_native_quest_session import (
    simulate_native_quest_session,NativeQuestSessionError,
)
from skeleton.jeeves.game_frontier_native_quest_batch import (
    replay_native_quest_batches,verify_native_quest_batch_report,
)


class NativeQuestBatchTests(unittest.TestCase):
    def setUp(self):
        source=NativeQuestSessionTests("test_full_branch_progression_flags_cues_and_evidence_chain")
        source.setUp()
        self.addCleanup(source.doCleanups)
        self.fixture=source
        self.journal=source.journal
        self.pages=page_source()
        self.graph=graph()
        self.approved=source.approval()

    def replay(self,**opts):
        return replay_native_quest_batches(
            self.journal,self.pages,self.graph,self.approved,
            actor_id="hero",scene_candidate_digest="d"*64,**opts)

    def test_all_window_sizes_preserve_quest_and_gdd_history(self):
        reference=simulate_native_quest_session(
            self.journal,self.pages,self.graph,self.approved,
            actor_id="hero",scene_candidate_digest="d"*64)
        for size in (1,2,3,4,5):
            with self.subTest(frames_per_window=size):
                data=self.replay(frames_per_window=size)
                self.assertEqual(data["verified_frame_count"],5)
                self.assertEqual(data["window_count"],(5+size-1)//size)
                self.assertEqual(data["total_approved_events"],3)
                self.assertEqual(data["head_checkpoint"]["quests"],
                                 reference["final_quests"])
                self.assertEqual(data["head_checkpoint"]["flags"],
                                 reference["final_flags"])
                self.assertEqual(data["head_checkpoint"]["last_session_receipt_digest"],
                                 reference["last_session_receipt_digest"])
                self.assertTrue(verify_native_quest_batch_report(
                    self.journal,self.pages,self.graph,self.approved,data,
                    actor_id="hero",scene_candidate_digest="d"*64,
                    frames_per_window=size))
                self.assertEqual(len(data["batch_chain_head_digest"]),64)

    def test_source_bound_resume_continues_without_reset(self):
        first=self.replay(through_frame=1,frames_per_window=1)
        tail=self.replay(through_frame=4,frames_per_window=2,
                         resume_checkpoint=first["head_checkpoint"],
                         expected_checkpoint_digest=first["head_checkpoint"]["receipt_digest"])
        complete=self.replay(frames_per_window=1)
        self.assertEqual(tail["start_frame"],2)
        self.assertEqual(tail["verified_frame_count"],3)
        self.assertEqual(tail["newly_approved_events"],1)
        self.assertEqual(tail["head_checkpoint"],complete["head_checkpoint"])
        self.assertEqual(tail["total_approved_events"],3)

    def test_missing_trusted_resume_or_noncontiguous_windows_rejected(self):
        first=self.replay(through_frame=1)
        for opts in (
            {"frames_per_window":0},
            {"frames_per_window":4097},
            {"through_frame":7},
            {"through_frame":1,"resume_checkpoint":first["head_checkpoint"],
             "expected_checkpoint_digest":first["head_checkpoint"]["receipt_digest"]},
            {"through_frame":4,"resume_checkpoint":first["head_checkpoint"]},
            {"expected_checkpoint_digest":"a"*64},
        ):
            with self.subTest(opts=opts),self.assertRaises(NativeQuestSessionError):
                self.replay(**opts)

    def test_tampered_window_receipt_detected(self):
        result=self.replay(frames_per_window=2)
        bad=deepcopy(result)
        bad["window_evidence"][1]["approved_pages"]=999
        with self.assertRaises(NativeQuestSessionError):
            verify_native_quest_batch_report(
                self.journal,self.pages,self.graph,self.approved,bad,
                actor_id="hero",scene_candidate_digest="d"*64,
                frames_per_window=2)
