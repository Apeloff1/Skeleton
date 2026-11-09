"""Source-replayed, explicit-approval native RPG quest session integration."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage,
    evaluate_environment_events,
)
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_rpg_bridge import native_rpg_observations
from skeleton.jeeves.game_frontier_native_quest_session import (
    NativeQuestSessionError, parse_native_quest_graph,
    authored_page_digest, simulate_native_quest_session,
    verify_native_quest_session,
)
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from tests.test_game_frontier_native_chunks import sample
from tests.test_game_frontier_position_frames import gdd


def sha(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def graph():
    return {"schema":"skeleton.game.native_quest_graph.v1","quests":[{
        "id":"chapter_1","title":"The Wind Islands",
        "start":"start",
        "stages":[
            {"id":"start","objective":"Watch the fall","next":["middle","alternate"]},
            {"id":"middle","objective":"Pass the doorway","next":["ending"]},
            {"id":"alternate","objective":"Search the ridge","next":["ending"]},
            {"id":"ending","objective":"Finish the route","next":[]},
        ],
    }]}


def page_source():
    condition=(EnvironmentalTrigger("fall_speed_mps","at_least",10.),)
    return (
        RPGEventPage("begin",80,condition,(
            RPGEventAction("start_quest","quest","hero","chapter_1"),
            RPGEventAction("set_flag","world","hero","quest_active=true"),
        ),repeat=False),
        RPGEventPage("gate",60,condition,(
            RPGEventAction("advance_quest","quest","hero","chapter_1:middle"),
            RPGEventAction("set_flag","world","hero","door_open=true"),
        ),required_flags=(("quest_active",True),),repeat=False),
        RPGEventPage("ending",40,condition,(
            RPGEventAction("advance_quest","quest","hero","chapter_1:ending"),
            RPGEventAction("show_dialogue","ui","hero","chapter-complete"),
        ),required_flags=(("door_open",True),),repeat=False),
    )


class NativeQuestSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.gdd=bind_signed_gdd(gdd())
        self.journal=FrameReceiptJournal(
            Path(self.temporary.name)/"quest.sqlite",self.gdd)
        self.addCleanup(self.journal.close)
        ingest=GodotPhysicsCaptureIngestor(
            self.journal,candidate_digest="d"*64,
            allowed_assets={"hero":"a"*64,"npc":"b"*64,"island":"c"*64})
        for i in range(5):
            ingest.ingest(sample(i,self.gdd.source_digest))

    def approval(self,pages=None,authorized=(0,1,2),quest=None):
        pages=pages or page_source()
        quest=quest or graph()
        flags={}
        completed=set()
        last={}
        entries=[]
        previous=None
        for index in range(5):
            actor=native_rpg_observations(self.journal.native_sample(index),
                                          actor_id="hero")
            frame,_=self.journal.load(index)
            decision=evaluate_environment_events(
                pages,current=actor,previous=previous,now_ms=frame.time_ns//1_000_000,
                flags=flags,last_fired_ms=last,completed_once=frozenset(completed))
            for proposal in decision.accepted:
                last[proposal.page_id]=frame.time_ns//1_000_000
                completed.add(proposal.page_id)
                if index in authorized:
                    entries.append({
                        "frame":index,"page_id":proposal.page_id,
                        "event_evidence_digest":proposal.evidence_digest,
                        "frame_receipt_digest":frame.receipt_digest,
                    })
                    for action in proposal.actions:
                        if action.kind=="set_flag":
                            name,truth=action.value.split("=",1)
                            flags[name]=(truth=="true")
            previous=actor
        report={
            "schema":"skeleton.game.native_quest_approvals.v1",
            "session_id":"local-quest-demo",
            "actor_id":"hero","track":"production",
            "signed_gdd_digest":self.gdd.source_digest,
            "authored_pages_digest":authored_page_digest(pages),
            "quest_graph_digest":parse_native_quest_graph(quest)["receipt_digest"],
            "initial_flags":{},"approvals":entries,
        }
        report["receipt_digest"]=sha(report)
        return report

    def run_session(self,approval=None,pages=None,quest=None,**kwargs):
        pages=pages or page_source()
        quest=quest or graph()
        approval=approval if approval is not None else self.approval(pages,quest=quest)
        return simulate_native_quest_session(
            self.journal,pages,quest,approval,actor_id="hero",
            scene_candidate_digest=kwargs.pop("scene_candidate_digest","d"*64),
            **kwargs)

    def test_full_branch_progression_flags_cues_and_evidence_chain(self):
        report=self.run_session()
        self.assertEqual(report["source_prefix_verified_frames"],5)
        self.assertEqual(report["approved_page_count"],3)
        self.assertEqual(report["final_quests"]["chapter_1"]["stage"],"ending")
        self.assertTrue(report["final_quests"]["chapter_1"]["completed"])
        self.assertEqual(report["final_quests"]["chapter_1"]["last_transition_frame"],2)
        self.assertEqual(report["final_flags"],{
            "quest_active":True,"door_open":True})
        self.assertEqual([len(f["approved_pages"]) for f in report["entries"]],
                         [1,1,1,0,0])
        self.assertEqual(report["entries"][2]["presentation_cues"][0]["state"],
                         "queued_not_dispatched")
        self.assertEqual(report["entries"][1]["previous_session_receipt_digest"],
                         report["entries"][0]["receipt_digest"])
        self.assertTrue(verify_native_quest_session(
            self.journal,page_source(),graph(),self.approval(),report,
            actor_id="hero",scene_candidate_digest="d"*64))
        self.assertEqual(report,self.run_session())

    def test_pagination_preserves_approved_prefix_and_one_shot(self):
        whole=self.run_session()
        paged=self.run_session(start_frame=3,through_frame=4,limit=2)
        self.assertEqual(paged["final_quests"],whole["final_quests"])
        self.assertEqual(paged["final_flags"],whole["final_flags"])
        self.assertEqual(paged["last_session_receipt_digest"],
                         whole["last_session_receipt_digest"])
        self.assertEqual([e["frame"] for e in paged["entries"]],[3,4])
        self.assertEqual(paged["approved_page_count"],3)

    def test_zero_approvals_cannot_progress_quests_or_flags(self):
        approval=self.approval(authorized=())
        report=self.run_session(approval=approval)
        self.assertEqual(report["approved_page_count"],0)
        self.assertEqual(report["final_quests"],{})
        self.assertEqual(report["final_flags"],{})
        self.assertTrue(report["entries"][0]["proposals"])
        self.assertTrue(all(not p["operator_approved"] for e in report["entries"]
                            for p in e["proposals"]))

    def test_rejects_tampered_approval_event_frame_gdd_or_quest_graph(self):
        for change in ("event","frame","gdd","graph","duplicate","future","actor"):
            approval=self.approval()
            if change=="event":
                approval["approvals"][0]["event_evidence_digest"]="0"*64
            if change=="frame":
                approval["approvals"][0]["frame_receipt_digest"]="0"*64
            if change=="gdd":
                approval["signed_gdd_digest"]="a"*64
            if change=="graph":
                approval["quest_graph_digest"]="b"*64
            if change=="duplicate":
                approval["approvals"].append(dict(approval["approvals"][0]))
            if change=="future":
                approval["approvals"][0]["frame"]=500
            if change=="actor":
                approval["actor_id"]="npc"
            approval["receipt_digest"]=sha({k:v for k,v in approval.items()
                                           if k!="receipt_digest"})
            with self.subTest(change=change),self.assertRaises(NativeQuestSessionError):
                self.run_session(approval=approval)

    def test_unexpected_unmatched_approval_and_forged_scene_fail_closed(self):
        original=self.approval()
        original["approvals"][1]["page_id"]="unseen"
        original["receipt_digest"]=sha({k:v for k,v in original.items()
                                        if k!="receipt_digest"})
        with self.assertRaises(NativeQuestSessionError):
            self.run_session(approval=original)
        with self.assertRaises(NativeQuestSessionError):
            self.run_session(scene_candidate_digest="0"*64)
        with self.assertRaises(NativeQuestSessionError):
            self.run_session(start_frame=4,through_frame=2)

    def test_quest_graph_rejects_disconnected_branches_cycles_and_digests(self):
        known=parse_native_quest_graph(graph())
        self.assertEqual(known,parse_native_quest_graph(known))
        for problem in ("missing","orphan","duplicate","endless","tamper"):
            quest=deepcopy(graph())
            stages=quest["quests"][0]["stages"]
            if problem=="missing":
                stages[0]["next"].append("absent")
            if problem=="orphan":
                stages[0]["next"].remove("alternate")
            if problem=="duplicate":
                stages.append(dict(stages[0]))
            if problem=="endless":
                stages[-1]["next"]=["middle"]
                stages[0]["next"]=["middle","alternate"]
            if problem=="tamper":
                quest=deepcopy(known)
                quest["quests"][0]["title"]="new plot"
            with self.subTest(problem=problem),self.assertRaises(NativeQuestSessionError):
                parse_native_quest_graph(quest)

    def test_unapproved_world_impact_action_never_executes_and_approved_rejects(self):
        hostile=(RPGEventPage("spawn",10,(
            EnvironmentalTrigger("native_contact_count","at_least",1.),),(
            RPGEventAction("spawn_prefab","world","hero","boss"),),
            repeat=False),)
        approval=self.approval(pages=hostile,authorized=())
        no_exec=self.run_session(approval=approval,pages=hostile)
        self.assertEqual(no_exec["final_quests"],{})
        self.assertEqual(no_exec["approved_page_count"],0)
        approval=self.approval(pages=hostile,authorized=(0,))
        with self.assertRaisesRegex(NativeQuestSessionError,"real engine gateway"):
            self.run_session(approval=approval,pages=hostile)

    def test_illegal_quest_branch_is_transactionally_rejected(self):
        pages=list(page_source())
        pages[1]=RPGEventPage("gate",60,pages[1].conditions,(
            RPGEventAction("advance_quest","quest","hero","chapter_1:ending"),
            RPGEventAction("set_flag","world","hero","door_open=true"),
        ),required_flags=pages[1].required_flags,repeat=False)
        pages=tuple(pages)
        with self.assertRaisesRegex(NativeQuestSessionError,"unauthorized quest branch"):
            self.run_session(pages=pages,approval=self.approval(pages=pages))

    def test_replay_audits_cue_and_state_mutation(self):
        report=self.run_session()
        altered=deepcopy(report)
        altered["entries"][2]["presentation_cues"][0]["cue"]="new dialogue"
        with self.assertRaisesRegex(NativeQuestSessionError,"chain differs"):
            verify_native_quest_session(
                self.journal,page_source(),graph(),self.approval(),altered,
                actor_id="hero",scene_candidate_digest="d"*64)


if __name__=="__main__":
    unittest.main()
