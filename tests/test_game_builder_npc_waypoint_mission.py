"""Original source NPC missions: fully routed witnessed quests, no fake progress."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from io import StringIO
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_chunked_npc_world import run_chunked_npc_world
from skeleton.ai.game_builder.advanced_npc_waypoint_mission import (
    SCHEMA, OriginalMissionError,
    run_original_npc_waypoint_mission, verify_original_npc_waypoint_mission,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def scene(citizens=16,chunks=3,seed=0):
    return run_chunked_npc_world([],seed=seed,options={
        "chunks_per_side":chunks,"citizens":citizens,
        "active_limit":8,"chunk_radius":1,"lod_policy":"fair",
    })


QUEST = [
    {"kind":"site","index":0,"action":"harvest"},
    {"kind":"npc","index":0,"action":"speak"},
    {"kind":"npc","index":0,"action":"support"},
    *[{"kind":"site","index":0,"action":"repair"} for _ in range(5)],
    {"kind":"site","index":0,"action":"claim"},
]


class OriginalNPCWaypointMissionTests(unittest.TestCase):
    def test_playable_nine_leg_original_quest_is_earned_not_invented(self):
        original=scene()
        mission=run_original_npc_waypoint_mission(original,QUEST)
        self.assertTrue(verify_original_npc_waypoint_mission(mission))
        self.assertEqual(mission["schema"],SCHEMA)
        self.assertEqual(mission["source_world_digest"],original["digest"])
        self.assertEqual(mission["completed_waypoint_count"],9)
        self.assertEqual(len(mission["legs"]),9)
        summary=mission["final_world_summary"]
        self.assertEqual(summary["real_quest_milestones"],1)
        self.assertEqual(summary["real_physical_events"],1)
        self.assertEqual(summary["firsthand_dialogues"],1)
        self.assertEqual(summary["paid_social_choices"],1)
        self.assertGreater(summary["actual_npc_movements"],0)
        self.assertEqual(mission["legs"][0]["firsthand_physical_facts_added"],1)
        self.assertEqual(mission["legs"][1]["genuine_dialogues_added"],1)
        self.assertEqual(mission["legs"][2]["paid_social_choices_added"],1)
        self.assertEqual(mission["legs"][-1]["quest_milestones_after"],1)
        self.assertTrue(all(item["arrived"] for item in mission["legs"]))
        self.assertTrue(all(item["result_head"] for item in mission["legs"]))
        self.assertFalse(mission["native_hardware_certified"])
        self.assertFalse(mission["original_project_files_mutated"])
        self.assertFalse(mission["model_weights_promoted"])

    def test_all_segments_execute_actual_source_actions_and_conserve_time(self):
        original=scene()
        mission=run_original_npc_waypoint_mission(original,QUEST)
        self.assertEqual(mission["total_real_actions"],
                         len(mission["generated_actions"]))
        self.assertEqual(sum(len(x["actual_actions"]) for x in mission["legs"]),
                         mission["total_real_actions"])
        previous=original["head_digest"]
        clock=original["state"]["tick"]
        for number,leg in enumerate(mission["legs"]):
            self.assertEqual(leg["leg"],number)
            self.assertEqual(leg["start_head"],previous)
            self.assertEqual(leg["start_tick"],clock)
            self.assertEqual(leg["end_tick"]-leg["start_tick"],
                             len(leg["actual_actions"]))
            self.assertEqual(leg["source_interaction_executed"],
                             leg["objective"]["action"] != "approach")
            self.assertTrue(all(r["source_frame"] for r in leg["source_action_receipts"]))
            previous=leg["result_head"]
            clock=leg["end_tick"]
        self.assertEqual(previous,mission["final_source_head"])
        self.assertEqual(clock,mission["final_world_summary"]["world_tick"])
        actual=run_chunked_npc_world(
            mission["generated_actions"],original["settings"],
            scenes=original["source_scenes"],seed=original["seed"],
            options=original["options"])
        self.assertEqual(actual["digest"],mission["final_world_digest"])

    def test_preexisting_world_history_is_preserved_before_explicit_itinerary(self):
        previous=run_chunked_npc_world(["wait","wait"],
                  options={"chunks_per_side":3,"citizens":16,"active_limit":8,
                           "lod_policy":"fair","chunk_radius":1})
        mission=run_original_npc_waypoint_mission(
            previous,[{"kind":"site","index":0,"action":"harvest"}])
        self.assertTrue(verify_original_npc_waypoint_mission(mission))
        self.assertEqual(mission["legs"][0]["start_tick"],2)
        self.assertEqual(mission["legs"][0]["start_head"],previous["head_digest"])
        self.assertEqual(mission["final_world_summary"]["real_physical_events"],1)

    def test_large_128_person_origins_keep_exact_actor_budget_and_source_outcomes(self):
        for citizens in (64,128):
            for chunks in (3,5):
                with self.subTest(citizens=citizens,chunks=chunks):
                    original=scene(citizens=citizens,chunks=chunks)
                    plan=run_original_npc_waypoint_mission(original,[
                        {"kind":"site","index":0,"action":"harvest"},
                        {"kind":"site","index":0,"action":"approach"},
                    ],max_steps_per_leg=12)
                    self.assertTrue(verify_original_npc_waypoint_mission(plan))
                    self.assertEqual(plan["final_world_summary"]["physical_npcs"],citizens)
                    self.assertEqual(plan["final_world_summary"]["real_physical_events"],1)
                    self.assertEqual(plan["completed_waypoint_count"],2)
                    self.assertGreaterEqual(plan["total_real_actions"],1)
                    self.assertEqual(plan["legs"][1]["actual_actions"],[])

    def test_no_claim_without_five_paid_physical_repairs(self):
        for itinerary in (
            [QUEST[-1]],
            [QUEST[0],QUEST[-1]],
            QUEST[:3]+QUEST[-1:],
            QUEST[:4]+QUEST[-1:],
            [QUEST[0],QUEST[1],QUEST[2],{"kind":"site","index":0,"action":"claim"}],
        ):
            with self.subTest(itinerary=itinerary):
                with self.assertRaises(OriginalMissionError):
                    run_original_npc_waypoint_mission(scene(),itinerary)

    def test_original_quest_requires_actual_firsthand_npc_interaction(self):
        for itinerary in (
            [QUEST[0],QUEST[2]],
            [QUEST[0],QUEST[3]],
            [QUEST[0],{"kind":"npc","index":5,"action":"support"}],
        ):
            with self.subTest(itinerary=itinerary):
                with self.assertRaises(OriginalMissionError):
                    run_original_npc_waypoint_mission(scene(),itinerary)

    def test_goal_and_turn_bounds_fail_closed_with_strict_types(self):
        source=scene()
        for bad in ([],[None],["harvest:0"],[{"kind":"site","index":0}],
                    [QUEST[0]]*13,[{"kind":"npc","index":True,"action":"speak"}],
                    [{"kind":"cell","index":100000,"action":"approach"}]):
            with self.subTest(bad=bad):
                with self.assertRaises(OriginalMissionError):
                    run_original_npc_waypoint_mission(source,bad)
        for budget in (0,73,True,-1,"8"):
            with self.subTest(budget=budget):
                with self.assertRaises(OriginalMissionError):
                    run_original_npc_waypoint_mission(source,[QUEST[0]],
                                                     max_steps_per_leg=budget)

    def test_source_and_exact_mission_history_forgery_never_earns_progress(self):
        record=run_original_npc_waypoint_mission(scene(),QUEST)
        for mutate in (
            lambda r:r["starting_world"]["state"]["actors"][0].__setitem__("position",900),
            lambda r:r["legs"][0].__setitem__("source_interaction_executed",False),
            lambda r:r["legs"][1]["objective"].__setitem__("index",5),
            lambda r:r["legs"][-1].__setitem__("quest_milestones_after",10),
            lambda r:r["legs"][0]["source_action_receipts"][-1].__setitem__("source_frame","0"*64),
            lambda r:r.__setitem__("total_real_actions",0),
            lambda r:r.__setitem__("final_world_digest","0"*64),
            lambda r:r["final_world_summary"].__setitem__("remaining_supplies",999),
            lambda r:r.__setitem__("model_weights_promoted",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            bad=deepcopy(record);mutate(bad)
            with self.subTest(mutate=mutate):
                with self.assertRaises(OriginalMissionError):
                    verify_original_npc_waypoint_mission(bad)


class OriginalNPCMissionSurfaces(unittest.TestCase):
    def test_offline_mission_cli_and_forged_replay_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);gamefile=p/"game.json";goals=p/"goals.json";save=p/"mission.json"
            gamefile.write_text(json.dumps(scene()),encoding="utf-8")
            goals.write_text(json.dumps(QUEST),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["plan-original-npc-mission","--record",str(gamefile),
                                      "--waypoints",str(goals)]),0)
            result=json.loads(output.getvalue())
            self.assertEqual(result["final_world_summary"]["real_quest_milestones"],1)
            save.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-original-npc-mission",
                                      "--record",str(save)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            result["final_world_summary"]["real_quest_milestones"]=999
            save.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-original-npc-mission",
                                      "--record",str(save)]),2)

    def test_authenticated_studio_proves_original_npc_mission_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_playable_mission","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,payload,auth=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=24)
                headers={"Content-Type":"application/json"}
                if auth: headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(payload),headers)
                res=conn.getresponse();status,body=res.status,json.loads(res.read())
                conn.close();return status,body
            try:
                params={"record":scene(),"waypoints":QUEST}
                self.assertEqual(post("/api/plan-original-npc-mission",params,False)[0],403)
                status,result=post("/api/plan-original-npc-mission",params)
                self.assertEqual(status,200)
                self.assertTrue(result["verified"])
                self.assertFalse(result["source_files_mutated"])
                self.assertEqual(result["record"]["final_world_summary"]["real_quest_milestones"],1)
                status,verified=post("/api/verify-original-npc-mission",{
                    "record":result["record"]})
                self.assertEqual(status,200)
                self.assertTrue(verified["verified"])
                tampered=deepcopy(result["record"])
                tampered["legs"][-1]["result_head"]="0"*64
                self.assertEqual(post("/api/verify-original-npc-mission",{
                    "record":tampered})[0],400)
                self.assertIn("NPC Waypoint Mission",
                              render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
