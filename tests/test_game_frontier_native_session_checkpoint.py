"""Real Godot journal checkpoint continuation, adversarial source and paging."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_native_session_checkpoint import (
    advance_native_quest_window, verify_native_quest_window,
)
from skeleton.jeeves.game_frontier_native_quest_session import (
    NativeQuestSessionError,
    simulate_native_quest_session,
)
from skeleton.jeeves.game_frontier_receipt_journal import FrameJournalError
from tests.test_game_frontier_native_quest_session import (
    NativeQuestSessionTests,graph,page_source,sha,
)


class NativeQuestCheckpointTests(unittest.TestCase):
    def setUp(self):
        fixture=NativeQuestSessionTests("test_full_branch_progression_flags_cues_and_evidence_chain")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.journal=fixture.journal
        self.pages=page_source()
        self.graph=graph()
        self.approvals=fixture.approval()

    def step(self, *, through, checkpoint=None, approvals=None, pages=None,
             graph_source=None, actor="hero", source="d"*64, max_frames=256,
             trusted_root=None):
        return advance_native_quest_window(
            self.journal,pages or self.pages,graph_source or self.graph,
            approvals if approvals is not None else self.approvals,
            actor_id=actor,scene_candidate_digest=source,
            through_frame=through,previous_checkpoint=checkpoint,
            expected_checkpoint_digest=(trusted_root if trusted_root is not None
                else checkpoint["receipt_digest"] if checkpoint is not None else None),
            max_frames=max_frames)

    def test_four_window_replay_matches_monolithic_quest_actions_and_recipts(self):
        whole=simulate_native_quest_session(
            self.journal,self.pages,self.graph,self.approvals,
            actor_id="hero",scene_candidate_digest="d"*64)
        receipt=None
        captured=[]
        windows=[]
        for frame in (0,1,2,4):
            result=self.step(through=frame,checkpoint=receipt)
            windows.append(result)
            captured.extend(result["entries"])
            self.assertTrue(verify_native_quest_window(
                self.journal,self.pages,self.graph,self.approvals,result,
                actor_id="hero",scene_candidate_digest="d"*64,
                through_frame=frame,previous_checkpoint=receipt,
                expected_checkpoint_digest=(
                    receipt["receipt_digest"] if receipt is not None else None)))
            receipt=result["checkpoint"]
        self.assertEqual(captured,whole["entries"])
        self.assertEqual(receipt["quests"],whole["final_quests"])
        self.assertEqual(receipt["flags"],whole["final_flags"])
        self.assertEqual(receipt["last_session_receipt_digest"],
                         whole["last_session_receipt_digest"])
        self.assertEqual([e["approved_page_count_delta"] for e in windows],
                         [1,1,1,0])
        self.assertEqual(receipt["approved_page_count"],3)
        self.assertEqual(receipt["frame"],4)
        self.assertEqual([w["verified_window_frames"] for w in windows],[1,1,1,2])
        self.assertEqual(windows[-1]["previous_checkpoint_digest"],
                         windows[-2]["checkpoint"]["receipt_digest"])

    def test_unapproved_events_still_suppress_once_on_resume(self):
        no_approvals=self.fixture.approval(authorized=())
        first=self.step(through=0,approvals=no_approvals)
        later=self.step(through=4,checkpoint=first["checkpoint"],
                        approvals=no_approvals)
        self.assertEqual(later["checkpoint"]["approved_page_count"],0)
        self.assertEqual(later["checkpoint"]["quests"],{})
        self.assertIn("begin",later["checkpoint"]["completed_once_page_ids"])
        self.assertNotIn("begin",[
            p["page_id"] for e in later["entries"] for p in e["proposals"]])

    def test_changing_or_inventing_past_approval_is_not_allowed(self):
        initial=self.step(through=0)
        original=initial["checkpoint"]
        for variant in ("removed","new","changed"):
            selected=deepcopy(self.approvals)
            if variant=="removed":
                selected["approvals"].pop(0)
            if variant=="new":
                selected["approvals"].append({
                    "frame":0,"page_id":"unobserved",
                    "event_evidence_digest":"a"*64,
                    "frame_receipt_digest":"b"*64,
                })
            if variant=="changed":
                selected["approvals"][0]["event_evidence_digest"]="f"*64
            selected["receipt_digest"]=sha({k:v for k,v in selected.items()
                                            if k!="receipt_digest"})
            with self.subTest(variant=variant),self.assertRaises(NativeQuestSessionError):
                self.step(through=1,checkpoint=original,approvals=selected)

    def test_corrupted_checkpoint_and_rehashed_false_state_rejected(self):
        initial=self.step(through=1)
        valid=initial["checkpoint"]
        for variant in ("root","flags","stage","sensor","native","page_history",
                        "old_frame","actor","scene","cooldown"):
            fake=deepcopy(valid)
            if variant=="root":
                fake["receipt_digest"]="0"*64
            elif variant=="flags":
                fake["flags"]["forged_win"]=True
            elif variant=="stage":
                fake["quests"]["chapter_1"]["stage"]="ending"
            elif variant=="sensor":
                fake["previous_observations"]["fall_speed_mps"]=999.
            elif variant=="native":
                fake["native_source_digest"]="0"*64
            elif variant=="page_history":
                fake["approved_rows"][0]["page_id"]="impostor"
            elif variant=="old_frame":
                fake["frame_receipt_digest"]="0"*64
            elif variant=="actor":
                fake["actor_id"]="npc"
            elif variant=="scene":
                fake["scene_candidate_digest"]="0"*64
            elif variant=="cooldown":
                fake["last_fired_ms"]["begin"]=99999999
            if variant!="root":
                fake["receipt_digest"]=sha({
                    k:v for k,v in fake.items() if k!="receipt_digest"})
            with self.subTest(variant=variant),self.assertRaises(
                (NativeQuestSessionError,FrameJournalError)):
                self.step(through=2,checkpoint=fake,
                          trusted_root=valid["receipt_digest"])

    def test_tampering_with_sqlite_source_rejected_during_resume(self):
        initial=self.step(through=1)
        with sqlite3.connect(self.fixture.db if hasattr(self.fixture,"db")
                             else self.journal.path) as db:
            # CAS corruption must be caught even when the original row hash
            # still points to the corrupted JSON body.
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest IN "
                       "(SELECT frame_digest FROM frontier_commits WHERE track='production' "
                       "AND frame=2)")
        with self.assertRaises((FrameJournalError,NativeQuestSessionError)):
            self.step(through=3,checkpoint=initial["checkpoint"])

    def test_window_bounds_and_frame_anchor_are_enforced(self):
        start=self.step(through=0)
        next_state=start["checkpoint"]
        for kwargs in (
            {"through":0,"checkpoint":next_state},
            {"through":4,"checkpoint":next_state,"max_frames":2},
            {"through":8,"checkpoint":next_state},
            {"through":1,"checkpoint":next_state,"actor":"other"},
            {"through":1,"checkpoint":next_state,"source":"0"*64},
        ):
            with self.subTest(kwargs=kwargs),self.assertRaises(
                (NativeQuestSessionError,FrameJournalError)):
                self.step(**kwargs)

    def test_integrity_report_rejects_forged_session_cue_and_progress(self):
        start=self.step(through=0)
        result=self.step(through=2,checkpoint=start["checkpoint"])
        corrupt=deepcopy(result)
        corrupt["checkpoint"]["quests"]["chapter_1"]["stage"]="middle"
        with self.assertRaises(NativeQuestSessionError):
            verify_native_quest_window(
                self.journal,self.pages,self.graph,self.approvals,corrupt,
                actor_id="hero",scene_candidate_digest="d"*64,
                through_frame=2,previous_checkpoint=start["checkpoint"],
                expected_checkpoint_digest=start["checkpoint"]["receipt_digest"])

    def test_segment_verifier_checks_anchored_game_source(self):
        first=self.journal.verify_native_segment(start_frame=0,through=4)
        self.assertEqual(first["verified_frames"],5)
        previous,_=self.journal.load(1)
        second=self.journal.verify_native_segment(
            start_frame=2,through=4,
            predecessor_frame_digest=previous.receipt_digest)
        self.assertEqual(second["verified_frames"],3)
        self.assertEqual(second["end_frame_digest"],first["end_frame_digest"])
        with self.assertRaises(FrameJournalError):
            self.journal.verify_native_segment(
                start_frame=2,through=4,predecessor_frame_digest="f"*64)
        with self.assertRaises(FrameJournalError):
            self.journal.verify_native_segment(start_frame=2,through=4)


if __name__=="__main__":
    unittest.main()
