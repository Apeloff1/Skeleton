"""CI-only Godot quest test-source selection and authored smoke fixture."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_game_frontier_smoke import build_smoke_project
from scripts.build_game_frontier_quest_smoke_approvals import select_fixture_approvals
from skeleton.jeeves.game_frontier_native_quest_session import (
    parse_native_quest_graph,authored_page_digest,
)
from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages


def digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def fake_timeline():
    entries=[]
    for i,which in ((1,"begin_sky_trial"),(4,"complete_sky_trial")):
        payload={
            "frame":i,"frame_receipt_digest":hex(i)[2:].zfill(64),
            "source_actor_id":"hero","signed_gdd_digest":"g"*64,
            "accepted_proposals":[{
                "page_id":which,"event_evidence_digest":hex(i+8)[2:].zfill(64),
            }],
        }
        payload["receipt_digest"]=digest(payload)
        entries.append(payload)
    data={
        "schema":"skeleton.game.native_rpg_event_timeline.v1",
        "actor_id":"hero","track":"production",
        "signed_gdd_digest":"g"*64,
        "authored_pages_digest":"p"*64,
        "start_frame":0,"entries":entries,
    }
    data["receipt_digest"]=digest(data)
    return data


class NativeQuestSmokeFixtureTests(unittest.TestCase):
    def test_godot_project_writes_rpg_pages_and_quest_graph_for_all_rates(self):
        with TemporaryDirectory() as root:
            home=Path(root)
            for fps in (30,50,60,120):
                folder=home/str(fps)
                folder.mkdir()
                build_smoke_project(folder,fps=fps,frames=20)
                pages=parse_native_rpg_pages(json.loads(
                    (folder/"native_rpg_pages.json").read_text()))
                graph=parse_native_quest_graph(json.loads(
                    (folder/"native_quest_graph.json").read_text()))
                self.assertEqual(len(pages),5)
                self.assertEqual({p.page_id for p in pages},{
                    "begin_sky_trial","complete_sky_trial",
                    "observed_actor_motion","entered_game_zone","exited_game_zone"})
                self.assertEqual(graph["quests"][0]["id"],"sky_trial")
                self.assertEqual(graph["quests"][0]["stages"][-1]["next"],[])
                self.assertEqual(graph["quests"][0]["stages"][0]["next"],["finished"])
                begin=next(p for p in pages if p.page_id=="begin_sky_trial")
                finish=next(p for p in pages if p.page_id=="complete_sky_trial")
                self.assertEqual({a.kind for a in begin.actions},
                                 {"start_quest","set_flag"})
                self.assertEqual(finish.actions[0].value,"sky_trial:finished")
                self.assertEqual(finish.required_flags,(("quest_active",True),))
                self.assertEqual(len(authored_page_digest(pages)),64)

    def select(self,timeline):
        return select_fixture_approvals(
            timeline,actor_id="hero",track="production",
            gdd_digest="g"*64,pages_digest="p"*64,
            graph_digest="q"*64)

    def test_select_only_observed_ordered_evidence_and_repeatable_digest(self):
        source=fake_timeline()
        approval=self.select(source)
        self.assertEqual([row["frame"] for row in approval["approvals"]],[1,4])
        self.assertEqual([row["page_id"] for row in approval["approvals"]],
                         ["begin_sky_trial","complete_sky_trial"])
        self.assertEqual(approval["initial_flags"],{})
        self.assertEqual(approval["receipt_digest"],digest({
            k:v for k,v in approval.items() if k!="receipt_digest"}))
        self.assertEqual(approval,self.select(source))

    def test_rejects_forged_actor_prefix_event_digest_and_reverse_order(self):
        for condition in ("actor","track","page_hash","frame","reversed","signature"):
            data=deepcopy(fake_timeline())
            if condition=="actor":
                data["actor_id"]="npc"
            if condition=="track":
                data["track"]="other"
            if condition=="page_hash":
                data["authored_pages_digest"]="0"*64
            if condition=="frame":
                data["entries"][1]["source_actor_id"]="npc"
            if condition=="reversed":
                data["entries"][0]["accepted_proposals"][0]["page_id"]="complete_sky_trial"
                data["entries"][1]["accepted_proposals"][0]["page_id"]="begin_sky_trial"
            if condition=="signature":
                data["entries"][1]["accepted_proposals"][0]["event_evidence_digest"]="0"*64
            if condition in ("frame","reversed"):
                for entry in data["entries"]:
                    entry["receipt_digest"]=digest({
                        k:v for k,v in entry.items() if k!="receipt_digest"})
            if condition!="signature":
                data["receipt_digest"]=digest({
                    k:v for k,v in data.items() if k!="receipt_digest"})
            with self.subTest(condition=condition),self.assertRaises(ValueError):
                self.select(data)


if __name__=="__main__":
    unittest.main()
