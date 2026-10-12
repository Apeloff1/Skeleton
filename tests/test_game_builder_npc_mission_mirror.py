"""Actual source-verified NPC mission contender review and defeated shortcuts."""
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
    run_original_npc_waypoint_mission, verify_original_npc_waypoint_mission,
)
from skeleton.ai.game_builder.advanced_npc_mission_mirror import (
    SCHEMA, OriginalMissionMirrorError,
    analyze_original_npc_missions, verify_original_npc_mission_mirror,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def source(citizens=16, chunks=3, seed=0):
    return run_chunked_npc_world([],seed=seed,options={
        "chunks_per_side":chunks,"citizens":citizens,
        "active_limit":8,"chunk_radius":1,"lod_policy":"fair",
    })


QUEST=[
    {"kind":"site","index":0,"action":"harvest"},
    {"kind":"npc","index":0,"action":"speak"},
    {"kind":"npc","index":0,"action":"support"},
    *[{"kind":"site","index":0,"action":"repair"} for _ in range(5)],
    {"kind":"site","index":0,"action":"claim"},
]
VARIANTS=[
    {"id":"full_restoration","waypoints":QUEST,"max_steps_per_leg":24},
    {"id":"harvest_only","waypoints":QUEST[:1],"max_steps_per_leg":16},
    {"id":"false_free_claim","waypoints":QUEST[-1:],"max_steps_per_leg":12},
    {"id":"silent_aid","waypoints":[QUEST[0],QUEST[2]],"max_steps_per_leg":12},
]


class OriginalMissionMirrorTests(unittest.TestCase):
    def test_real_original_success_partial_and_illegal_free_quest_are_separate(self):
        original=source()
        report=analyze_original_npc_missions(original,VARIANTS)
        self.assertTrue(verify_original_npc_mission_mirror(report))
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["submitted"],4)
        self.assertEqual(report["accepted_actual_routes"],2)
        self.assertEqual(report["rejected_actual_routes"],2)
        self.assertFalse(report["invalid_or_unproven_routes_promoted"])
        self.assertFalse(report["candidate_set_exhaustively_proven_optimal"])
        self.assertFalse(report["model_weights_promoted"])
        self.assertFalse(report["native_hardware_certified"])
        self.assertFalse(report["original_game_files_mutated"])
        success,partial,denied,impossible=report["reviews"]
        self.assertTrue(success["accepted"])
        self.assertEqual(success["outcome"]["new_earned_quests"],1)
        self.assertTrue(success["outcome"]["earned_material_quest"])
        self.assertEqual(success["outcome"]["completed_legs"],9)
        self.assertEqual(len(success["outcome"]["per_leg_causal_proof_digests"]),9)
        self.assertEqual(partial["outcome"]["completed_legs"],1)
        self.assertEqual(partial["outcome"]["new_earned_quests"],0)
        self.assertEqual(partial["outcome"]["new_physical_events"],1)
        self.assertEqual(denied["status"],"rejected_by_real_gameplay")
        self.assertIsNone(denied["outcome"])
        self.assertIsNone(impossible["outcome"])
        self.assertIn("full_restoration",report["pareto_source_verified_ids"])
        self.assertEqual(report["first_reviewed_candidate"],"full_restoration")

    def test_costs_and_event_receipts_match_real_source_missions(self):
        game=source()
        choices=[
            {"id":"full","waypoints":QUEST,"max_steps_per_leg":24},
            {"id":"mineral","waypoints":QUEST[:1],"max_steps_per_leg":16},
        ]
        report=analyze_original_npc_missions(game,choices)
        self.assertTrue(verify_original_npc_mission_mirror(report))
        for option,review in zip(choices,report["reviews"]):
            actual=run_original_npc_waypoint_mission(
                game,option["waypoints"],
                max_steps_per_leg=option["max_steps_per_leg"])
            self.assertTrue(verify_original_npc_waypoint_mission(actual))
            self.assertEqual(review["outcome"]["result_digest"],actual["final_world_digest"])
            self.assertEqual(review["outcome"]["actual_steps"],actual["total_real_actions"])
            self.assertEqual(review["outcome"]["remaining_supplies"],
                             actual["final_world_summary"]["remaining_supplies"])
            self.assertEqual(review["outcome"]["per_leg_source_receipt_heads"],
                             [x["result_head"] for x in actual["legs"]])
            self.assertEqual(review["outcome"]["detailed_npc_updates"]+
                             review["outcome"]["deferred_npc_turns"],
                             review["outcome"]["physical_population"]*
                             review["outcome"]["world_tick"])

    def test_none_of_the_failed_variants_may_enter_pareto_frontier(self):
        report=analyze_original_npc_missions(source(),VARIANTS)
        self.assertEqual(set(report["pareto_source_verified_ids"])-
                         {x["id"] for x in report["reviews"] if x["accepted"]},set())
        self.assertEqual(set(report["review_order"]),
                         {x["id"] for x in report["reviews"] if x["accepted"]})
        self.assertFalse(any(x["accepted"] for x in report["reviews"][2:]))

    def test_all_physical_128_npc_scene_sources_keep_stable_populations(self):
        for count in (64,128):
            for chunks in (3,5):
                with self.subTest(citizens=count,chunks=chunks):
                    game=source(citizens=count,chunks=chunks)
                    report=analyze_original_npc_missions(game,[
                        {"id":"harvest","waypoints":QUEST[:1],
                         "max_steps_per_leg":12},
                        {"id":"false_claim","waypoints":QUEST[-1:],
                         "max_steps_per_leg":12},
                    ])
                    self.assertTrue(verify_original_npc_mission_mirror(report))
                    self.assertEqual(report["accepted_actual_routes"],1)
                    self.assertEqual(report["rejected_actual_routes"],1)
                    self.assertEqual(report["reviews"][0]["outcome"]["physical_population"],count)

    def test_strict_candidate_schema_and_large_candidate_counts_rejected(self):
        game=source()
        for invalid in (
            [],[None],["harvest"],[{"id":"x","waypoints":[],"max_steps_per_leg":8}],
            [{"id":"x","waypoints":QUEST[:1],"max_steps_per_leg":True}],
            [{"id":"x","waypoints":QUEST[:1],"max_steps_per_leg":73}],
            [{"id":"capital LETTER","waypoints":QUEST[:1],"max_steps_per_leg":8}],
            [{"id":"x","waypoints":QUEST[:1],"max_steps_per_leg":8},
             {"id":"x","waypoints":QUEST[:1],"max_steps_per_leg":8}],
            [{"id":"x","waypoints":[{"kind":"site","index":True,"action":"harvest"}],
              "max_steps_per_leg":8}],
            [{"id":"x","waypoints":QUEST[:1],"max_steps_per_leg":8,
              "unauthorized":"yes"}],
            [VARIANTS[1]]*9,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(OriginalMissionMirrorError):
                    analyze_original_npc_missions(game,invalid)

    def test_adversarial_forgery_and_rank_manipulation_denied(self):
        original=analyze_original_npc_missions(source(),VARIANTS)
        for attack in (
            lambda x:x["reviews"][0]["outcome"].__setitem__("new_earned_quests",100),
            lambda x:x["reviews"][1]["outcome"].__setitem__("actual_steps",0),
            lambda x:x["reviews"][2].__setitem__("status","independently_replayed_real_game"),
            lambda x:x["reviews"][3].__setitem__("accepted",True),
            lambda x:x["reviews"][0]["outcome"]["per_leg_source_receipt_heads"].__setitem__(0,"0"*64),
            lambda x:x.__setitem__("pareto_source_verified_ids",["false_free_claim"]),
            lambda x:x.__setitem__("first_reviewed_candidate","harvest_only"),
            lambda x:x["original_source_world"]["state"]["actors"][0].__setitem__("position",999),
            lambda x:x.__setitem__("all_valid_routes_reexecuted_from_source",False),
            lambda x:x.__setitem__("model_weights_promoted",True),
            lambda x:x.__setitem__("digest","0"*64),
        ):
            forged=deepcopy(original);attack(forged)
            with self.subTest(attack=attack):
                with self.assertRaises(OriginalMissionMirrorError):
                    verify_original_npc_mission_mirror(forged)

    def test_real_source_seed_changes_scenario_evidence_not_logic(self):
        a=analyze_original_npc_missions(source(seed=0),[
            {"id":"harvest","waypoints":QUEST[:1],"max_steps_per_leg":12},
        ])
        b=analyze_original_npc_missions(source(seed=1),[
            {"id":"harvest","waypoints":QUEST[:1],"max_steps_per_leg":12},
        ])
        self.assertTrue(verify_original_npc_mission_mirror(a))
        self.assertTrue(verify_original_npc_mission_mirror(b))
        self.assertEqual(a["accepted_actual_routes"],1)
        self.assertEqual(b["accepted_actual_routes"],1)
        self.assertNotEqual(a["source_world_digest"],b["source_world_digest"])
        self.assertNotEqual(a["digest"],b["digest"])


class MissionMirrorProductTests(unittest.TestCase):
    def test_local_cli_round_trip_and_forged_source_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);orig=base/"scene.json";choices=base/"choices.json"
            reportfile=base/"report.json"
            orig.write_text(json.dumps(source()),encoding="utf-8")
            choices.write_text(json.dumps(VARIANTS[:2]),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli([
                    "analyze-original-npc-missions","--record",str(orig),
                    "--candidates",str(choices)]),0)
            report=json.loads(output.getvalue())
            self.assertEqual(report["accepted_actual_routes"],2)
            reportfile.write_text(json.dumps(report),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli([
                    "verify-original-npc-mission-mirror","--record",str(reportfile)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            report["reviews"][0]["outcome"]["remaining_supplies"]+=1000
            reportfile.write_text(json.dumps(report),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli([
                    "verify-original-npc-mission-mirror","--record",str(reportfile)]),2)

    def test_token_guarded_studio_does_not_promote_failed_missions(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_mission_adversarial","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def post(path,body,auth=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=24)
                h={"Content-Type":"application/json"}
                if auth: h["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),h)
                res=conn.getresponse();code,obj=res.status,json.loads(res.read())
                conn.close();return code,obj
            try:
                data={"record":source(),"candidates":VARIANTS[:2]}
                self.assertEqual(post("/api/analyze-original-npc-missions",data,False)[0],403)
                code,out=post("/api/analyze-original-npc-missions",data)
                self.assertEqual(code,200)
                self.assertTrue(out["verified"])
                self.assertEqual(out["record"]["accepted_actual_routes"],2)
                self.assertFalse(out["source_files_mutated"])
                self.assertFalse(out["model_weights_promoted"])
                code,checked=post("/api/verify-original-npc-mission-mirror",
                                  {"record":out["record"]})
                self.assertEqual(code,200)
                self.assertTrue(checked["verified"])
                bad=deepcopy(out["record"])
                bad["reviews"][0]["outcome"]["new_earned_quests"]=100
                self.assertEqual(post("/api/verify-original-npc-mission-mirror",
                                      {"record":bad})[0],400)
                self.assertIn("NPC Mission Mirror",render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
