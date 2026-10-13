"""Original NPC historical provenance index, competing real worlds and full replay."""
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

from skeleton.ai.game_builder.advanced_npc_provenance_index import (
    SCHEMA, KINDS, MAX_PAGE,
    analyze_original_npc_histories,verify_original_npc_histories,
)
from skeleton.ai.game_builder.advanced_chunked_npc_world import run_chunked_npc_world
from skeleton.ai.game_builder.advanced_chunked_world_timeline import (
    make_chunked_bookmarks,ChunkTimelineError,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html

STORY=["move:south","move:east","harvest:0","speak:0","support:0",
       *["repair:0"]*5,"claim:0"]
VARIANTS=[
    {"name":"restoration","actions":STORY},
    {"name":"neutrality","actions":["wait"]*len(STORY)},
]


class OriginalWorldHistoryIndexTests(unittest.TestCase):
    def test_real_earned_quest_is_distinguishable_from_a_passive_history(self):
        source=make_chunked_bookmarks(run_chunked_npc_world([]))
        report=analyze_original_npc_histories(source,VARIANTS,cursor=0)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertTrue(verify_original_npc_histories(report))
        self.assertEqual(report["source_cursor"],0)
        self.assertEqual(len(report["comparisons"]),2)
        first,second=report["comparisons"]
        self.assertEqual(first["metrics"]["quest_milestones"],1)
        self.assertEqual(second["metrics"]["quest_milestones"],0)
        self.assertEqual(first["real_earned_quests"][0]["ending"],"restored")
        self.assertEqual(first["real_earned_quests"][0]["followups"],5)
        self.assertTrue(first["real_earned_quests"][0]["actual_testimonies"])
        self.assertEqual(second["real_earned_quests"],[])
        self.assertNotEqual(first["source_head"],second["source_head"])
        self.assertNotEqual(first["world_digest"],second["world_digest"])
        self.assertEqual(first["metrics"]["people"],16)
        self.assertEqual(second["metrics"]["people"],16)
        self.assertFalse(report["model_weights_promoted"])
        self.assertFalse(report["native_hardware_benchmark_certified"])
        self.assertFalse(report["source_world_files_mutated"])
        self.assertTrue(report["records_reconstructed_from_actual_game_trace"])

    def test_true_physical_world_witness_fact_is_indexed_by_exact_action_head(self):
        checkpoint=make_chunked_bookmarks(run_chunked_npc_world([]))
        query={"kind":"physical_event"}
        result=analyze_original_npc_histories(checkpoint,VARIANTS,
                                              cursor=0,query=query)
        self.assertTrue(verify_original_npc_histories(result))
        self.assertEqual(result["matching_record_count"],1)
        event=result["records"][0]
        self.assertEqual(event["branch"],"restoration")
        self.assertEqual(event["kind"],"physical_event")
        self.assertEqual(event["step"],2)
        self.assertEqual(event["tick"],3)
        self.assertEqual(event["payload"]["source_kind"],"harvest")
        self.assertEqual(event["payload"]["source_event_id"],0)
        self.assertIn("original_chunk_npc:000",
                      event["payload"]["direct_witness_ids"])
        self.assertEqual(event["authority_head"],
                         result["comparisons"][0]["source_head"]
                         if event["step"]==len(STORY)-1
                         else run_chunked_npc_world(STORY)["trace"][2]["digest"])
        self.assertTrue(result["indexed_causal_record_counts"]["physical_event"]>0)

    def test_time_window_and_actor_filters_only_return_physically_valid_events(self):
        source=make_chunked_bookmarks(run_chunked_npc_world(["wait"]*8))
        options={"kind":"physical_move","actor_id":"original_chunk_npc:000",
                 "from_turn":0,"to_turn":12}
        report=analyze_original_npc_histories(source,
            [{"name":"original_schedule","actions":["wait"]*4}],cursor=8,
            query=options)
        self.assertTrue(verify_original_npc_histories(report))
        for row in report["records"]:
            self.assertEqual(row["kind"],"physical_move")
            self.assertEqual(row["payload"]["actor"],"original_chunk_npc:000")
            self.assertTrue(row["payload"]["one_tile"])
            self.assertTrue(0<=row["tick"]<=12)
        if report["records"]:
            self.assertEqual(report["records"][0]["inherited_source_prefix"],
                             report["records"][0]["step"]<8)

    def test_pagination_is_stable_disjoint_and_replayable_across_pages(self):
        source=make_chunked_bookmarks(run_chunked_npc_world(["wait"]*16))
        variants=[
            {"name":"a","actions":["wait","wait","wait"]},
            {"name":"b","actions":["move:west","move:east","wait"]},
        ]
        query={"kind":"action","limit":7,"offset":0}
        first=analyze_original_npc_histories(source,variants,cursor=8,query=query)
        self.assertEqual(first["matching_record_count"],22)
        self.assertEqual(first["returned_record_count"],7)
        self.assertEqual(first["next_offset"],7)
        second=analyze_original_npc_histories(source,variants,cursor=8,
                      query={**query,"offset":7})
        self.assertEqual(second["returned_record_count"],7)
        self.assertEqual(second["next_offset"],14)
        third=analyze_original_npc_histories(source,variants,cursor=8,
                      query={**query,"offset":14,"limit":48})
        self.assertEqual(third["returned_record_count"],8)
        self.assertIsNone(third["next_offset"])
        ids=lambda rows:[(r["branch"],r["step"],r["authority_head"]) for r in rows]
        complete=ids(first["records"]+second["records"]+third["records"])
        self.assertEqual(len(set(complete)),22)
        for r in (first,second,third):
            self.assertTrue(verify_original_npc_histories(r))

    def test_queries_reject_unsafe_malformed_actor_ids_and_unbounded_ranges(self):
        source=make_chunked_bookmarks(run_chunked_npc_world([]))
        for q in (
            {"kind":"unknown"}, {"kind":True}, {"offset":-1},
            {"offset":4097}, {"limit":0}, {"limit":MAX_PAGE+1},
            {"from_turn":100,"to_turn":9}, {"to_turn":129},
            {"from_turn":True}, {"actor_id":7},
            {"actor_id":"actor:999"}, {"actor_id":"original_chunk_npc:9"},
            {"actor_id":"original_chunk_npc:00a"}, {"typo":"anything"},
        ):
            with self.subTest(query=q):
                with self.assertRaises(ChunkTimelineError):
                    analyze_original_npc_histories(source,VARIANTS,
                                                   cursor=0,query=q)

    def test_forged_historical_evidence_refused_without_promoting_false_outcome(self):
        source=make_chunked_bookmarks(run_chunked_npc_world([]))
        report=analyze_original_npc_histories(source,VARIANTS,
                   cursor=0,query={"kind":"physical_event"})
        for attack in (
            lambda x:x["comparisons"][0]["metrics"].__setitem__("quest_milestones",99),
            lambda x:x["comparisons"][1]["delta_from_original_cursor"].__setitem__(
                "remaining_supplies",100000),
            lambda x:x["records"][0]["payload"].__setitem__("direct_witness_ids",[]),
            lambda x:x["records"][0].__setitem__("authority_head","0"*64),
            lambda x:x["indexed_causal_record_counts"].__setitem__("physical_event",0),
            lambda x:x["source_checkpoint"]["source_world"]["state"].__setitem__("completed",12),
            lambda x:x.__setitem__("matching_record_count",100),
            lambda x:x.__setitem__("model_weights_promoted",True),
            lambda x:x.__setitem__("digest","0"*64),
        ):
            tampered=deepcopy(report);attack(tampered)
            with self.subTest(attack=attack):
                with self.assertRaises(ChunkTimelineError):
                    verify_original_npc_histories(tampered)

    def test_source_expanded_world_and_seed_preserved_during_historical_inquiry(self):
        for seed in (0,1,5):
            options={"chunks_per_side":5,"citizens":32,
                     "active_limit":6,"chunk_radius":0}
            source=make_chunked_bookmarks(run_chunked_npc_world(["wait"]*8,
                                          seed=seed,options=options))
            report=analyze_original_npc_histories(source,
                   [{"name":"north","actions":["move:north"]},
                    {"name":"east","actions":["move:east"]}],cursor=8,
                   query={"kind":"action","limit":48})
            with self.subTest(seed=seed):
                self.assertTrue(verify_original_npc_histories(report))
                self.assertEqual(report["baseline_metrics"]["people"],32)
                self.assertEqual(report["source_cursor"],8)
                self.assertEqual(len(report["comparisons"]),2)

    def test_variants_require_individual_safe_unique_source_names_and_registered_commands(self):
        source=make_chunked_bookmarks(run_chunked_npc_world([]))
        for v in ([],
                  [{"name":"a","actions":[]},{"name":"a","actions":[]}],
                  [{"name":"forged name","actions":[]}],
                  [{"name":"a","actions":"wait"}],
                  [{"name":"a","actions":["evil"]}],
                  [{"name":"a","actions":[True]}],
                  [{"name":"a","actions":[],"extra":1}],
                  [{"name":"a","actions":[]}]*13):
            with self.subTest(variants=v):
                with self.assertRaises(ChunkTimelineError):
                    analyze_original_npc_histories(source,v)


class OriginalWorldHistoryInterfaces(unittest.TestCase):
    def test_offline_source_query_and_verifier_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"source.json";variants=root/"variants.json"
            query=root/"query.json";destination=root/"proof.json"
            source.write_text(json.dumps(make_chunked_bookmarks(
                run_chunked_npc_world(["wait"]*8))),encoding="utf-8")
            variants.write_text(json.dumps([{"name":"original","actions":["wait"]}]),
                                encoding="utf-8")
            query.write_text(json.dumps({"kind":"action","limit":12}),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["indexed-npc-histories","--checkpoint",str(source),
                   "--variants",str(variants),"--query",str(query),"--cursor","8"]),0)
            result=json.loads(output.getvalue())
            self.assertEqual(result["source_cursor"],8)
            self.assertEqual(result["matching_record_count"],9)
            destination.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-indexed-npc-histories",
                                      "--record",str(destination)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            result["records"][0]["payload"]["command"]="teleport"
            destination.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-indexed-npc-histories",
                                      "--record",str(destination)]),2)

    def test_studio_operator_auth_and_reviewed_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=GameWorkspace.create(Path(tmp)/"studio",authorized=True)
            ws.create_project("original_indexed_histories","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,auth=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=12)
                headers={"Content-Type":"application/json"}
                if auth:headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),headers)
                res=conn.getresponse()
                code,raw=res.status,res.read()
                conn.close()
                return code,json.loads(raw)
            try:
                packet={"checkpoint":make_chunked_bookmarks(
                        run_chunked_npc_world(["wait"]*8)),
                        "variants":[{"name":"walk","actions":["move:west"]}],
                        "cursor":8,"query":{"kind":"action","limit":4}}
                self.assertEqual(post("/api/indexed-npc-histories",packet,False)[0],403)
                status,res=post("/api/indexed-npc-histories",packet)
                self.assertEqual(status,200)
                self.assertTrue(res["verified"])
                self.assertFalse(res["source_files_mutated"])
                proof=res["record"]
                self.assertEqual(proof["returned_record_count"],4)
                status,verified=post("/api/indexed-npc-histories-verify",{"record":proof})
                self.assertEqual(status,200)
                self.assertTrue(verified["verified"])
                forged=deepcopy(proof)
                forged["comparisons"][0]["metrics"]["remaining_supplies"]=999
                self.assertEqual(post("/api/indexed-npc-histories-verify",
                                      {"record":forged})[0],400)
                self.assertIn("NPC History Index",render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
