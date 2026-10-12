"""Source-indexed chunk residency: replay-safe lookup, movement and real LOD."""
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

from skeleton.ai.game_builder.advanced_chunk_residency_index import (
    SCHEMA, QUERY_SCHEMA, ChunkIndexError, build_original_chunk_index,
    verify_original_chunk_index, query_original_chunk_index,
    verify_original_chunk_query,
)
from skeleton.ai.game_builder.advanced_chunked_npc_world import (
    run_chunked_npc_world, verify_chunked_npc_world,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def source(*,people=64,chunks=5,seed=0,commands=None):
    return run_chunked_npc_world(
        ["wait","wait","move:west","move:east"] if commands is None else commands,
        seed=seed,
        options={"chunks_per_side":chunks,"citizens":people,
                 "active_limit":8,"chunk_radius":1,"lod_policy":"fair"},
    )


class SourceChunkIndexTests(unittest.TestCase):
    def test_all_128_physical_bodies_are_indexed_once_on_full_source(self):
        game=source(people=128)
        self.assertTrue(verify_chunked_npc_world(game))
        report=build_original_chunk_index(game)
        self.assertTrue(verify_original_chunk_index(report))
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["source_game_digest"],game["digest"])
        self.assertEqual(report["source_head"],game["head_digest"])
        self.assertEqual(report["physical_actor_count"],128)
        self.assertEqual(len(report["buckets"]),25)
        all_bodies=[a for bucket in report["buckets"].values() for a in bucket]
        self.assertEqual(len(all_bodies),128)
        self.assertEqual(len({a["actor_id"] for a in all_bodies}),128)
        self.assertEqual(len({a["position"] for a in all_bodies}),128)
        self.assertNotIn(game["state"]["player"],
                         {a["position"] for a in all_bodies})
        self.assertEqual(
            report["detailed_updates_total"]+report["deferred_actor_turns_total"],
            len(game["commands"])*128)
        self.assertEqual(len(report["per_turn_lod_receipts"]),4)
        self.assertEqual(report["physical_movements_total"],
                         game["state"]["scheduler"]["physical_moves"])
        self.assertFalse(report["phantom_offscreen_progress"])
        self.assertFalse(report["model_weights_promoted"])
        self.assertFalse(report["native_engine_certified"])
        self.assertFalse(report["source_files_modified"])

    def test_actual_small_chunk_query_examines_only_resident_buckets(self):
        report=build_original_chunk_index(source(people=128))
        q=query_original_chunk_index(report,query={
            "center_chunk":[0,0],"radius":0,"limit":32,
        })
        self.assertTrue(verify_original_chunk_query(q))
        self.assertEqual(q["schema"],QUERY_SCHEMA)
        self.assertEqual(q["candidate_chunk_keys"],["0:0"])
        self.assertEqual(q["physical_actor_population"],128)
        self.assertLess(q["candidate_actor_entries_examined"],128)
        self.assertEqual(q["matching_actors"],
                         q["candidate_actor_entries_examined"])
        self.assertEqual(q["returned_count"],len(q["residents"]))
        for body in q["residents"]:
            side=report["side"];at=body["position"]
            self.assertEqual([at%side//7,at//side//7],[0,0])
            self.assertEqual(body["source_head"],report["source_head"])
        self.assertTrue(q["query_does_not_move_npcs_or_mint_witnesses"])
        self.assertFalse(q["hardware_speed_benchmark_claimed"])

    def test_only_exactly_scheduled_residents_are_detailed_this_turn(self):
        report=build_original_chunk_index(source(people=64,chunks=3))
        detailed=query_original_chunk_index(report,query={
            "center_chunk":[1,1],"radius":1,
            "mode":"detailed_this_turn","limit":32,
        })
        deferred=query_original_chunk_index(report,query={
            "center_chunk":[1,1],"radius":1,
            "mode":"deferred_this_turn","limit":32,
        })
        self.assertTrue(verify_original_chunk_query(detailed))
        self.assertTrue(verify_original_chunk_query(deferred))
        self.assertEqual(detailed["matching_actors"],8)
        self.assertEqual(deferred["matching_actors"],56)
        self.assertEqual({x["actor_id"] for x in detailed["residents"]},
                         set(report["source_game"]["state"]["detailed_actor_ids"]))
        self.assertTrue(all(x["actually_detailed_this_turn"]
                            for x in detailed["residents"]))
        self.assertTrue(all(not x["actually_detailed_this_turn"]
                            for x in deferred["residents"]))

    def test_pagination_and_exact_original_actor_id_filter(self):
        report=build_original_chunk_index(source(people=64,chunks=3))
        all_pages=[]
        offset=0
        while True:
            page=query_original_chunk_index(report,query={
                "center_chunk":[1,1],"radius":1,"limit":12,"offset":offset,
            })
            self.assertTrue(verify_original_chunk_query(page))
            all_pages.extend(page["residents"])
            if page["next_offset"] is None:break
            self.assertGreater(page["next_offset"],offset)
            offset=page["next_offset"]
        self.assertEqual(len(all_pages),64)
        self.assertEqual(len({x["actor_id"] for x in all_pages}),64)
        identity=all_pages[-1]["actor_id"]
        exactly=query_original_chunk_index(report,query={
            "center_chunk":[1,1],"radius":1,"actor_id":identity,
        })
        self.assertTrue(verify_original_chunk_query(exactly))
        self.assertEqual(exactly["matching_actors"],1)
        self.assertEqual(exactly["residents"][0]["actor_id"],identity)

    def test_source_moves_and_per_turn_fidelity_have_exact_chain_heads(self):
        game=source(people=96,chunks=5,commands=["wait"]*8)
        index=build_original_chunk_index(game)
        self.assertTrue(verify_original_chunk_index(index))
        self.assertEqual(len(index["per_turn_lod_receipts"]),8)
        for original,receipt in zip(game["trace"],index["per_turn_lod_receipts"]):
            self.assertEqual(receipt["tick"],original["tick"])
            self.assertEqual(receipt["source_head"],original["digest"])
            self.assertEqual(receipt["selected_actor_ids"],
                             original["lod_fidelity"]["selected_actor_ids"])
            self.assertEqual(receipt["detailed"],
                             original["lod_fidelity"]["actually_detailed"])
            self.assertEqual(receipt["deferred"],
                             original["lod_fidelity"]["deferred"])
        for migration in index["chunk_transfers"]:
            self.assertNotEqual(migration["from_chunk"],migration["to_chunk"])
            self.assertTrue(any(x["digest"]==migration["source_frame"]
                                for x in game["trace"]))
            side=game["state"]["side"]
            source_cell,destination=migration["from_cell"],migration["to_cell"]
            self.assertEqual(abs(source_cell%side-destination%side)+
                             abs(source_cell//side-destination//side),1)

    def test_existing_original_authored_quest_remains_indexable(self):
        story=["move:south","move:east","harvest:0","speak:0","support:0"]+[
            "repair:0"]*5+["claim:0"]
        game=source(people=16,chunks=3,commands=story)
        self.assertEqual(game["state"]["completed"],1)
        indexed=build_original_chunk_index(game)
        self.assertTrue(verify_original_chunk_index(indexed))
        self.assertEqual(indexed["tick"],len(story))
        self.assertEqual(len(indexed["per_turn_lod_receipts"]),len(story))
        result=query_original_chunk_index(indexed,query={
            "center_chunk":[1,1],"radius":0,"limit":32,
        })
        self.assertTrue(verify_original_chunk_query(result))
        self.assertTrue(indexed["source_game"]["state"]["events"][0]["direct_witnesses"])

    def test_index_and_query_tampering_cannot_forge_residency_or_lod(self):
        original=build_original_chunk_index(source(people=64,chunks=3))
        for attacker in (
            lambda x:x["buckets"]["1:1"][0].__setitem__("position",999),
            lambda x:x["buckets"]["1:1"].append({"actor_id":"fake"}),
            lambda x:x["per_turn_lod_receipts"][0].__setitem__("detailed",99),
            lambda x:x.__setitem__("physical_movements_total",999),
            lambda x:x["source_game"]["state"]["actors"][0].__setitem__("position",33),
            lambda x:x.__setitem__("model_weights_promoted",True),
            lambda x:x.__setitem__("digest","0"*64),
        ):
            bad=deepcopy(original);attacker(bad)
            with self.subTest(attacker=attacker):
                with self.assertRaises(ChunkIndexError):
                    verify_original_chunk_index(bad)
        query=query_original_chunk_index(original,query={"limit":12})
        for attacker in (
            lambda x:x["residents"][0].__setitem__("position",0),
            lambda x:x.__setitem__("candidate_actor_entries_examined",0),
            lambda x:x.__setitem__("original_source_fully_authenticated",False),
            lambda x:x["source_index"].__setitem__("source_head","fake"),
            lambda x:x.__setitem__("digest","0"*64),
        ):
            bad=deepcopy(query);attacker(bad)
            with self.subTest(attacker=attacker):
                with self.assertRaises(ChunkIndexError):
                    verify_original_chunk_query(bad)

    def test_strict_spatial_controls_and_types(self):
        record=build_original_chunk_index(source(people=16,chunks=3))
        for bad in (
            {"center_chunk":[-1,0]}, {"center_chunk":[3,0]},
            {"center_chunk":(1,1)}, {"center_chunk":[1,True]},
            {"radius":2}, {"radius":True}, {"mode":"predicted"},
            {"limit":0}, {"limit":33}, {"offset":129},
            {"actor_id":"original_chunk_npc:1"},
            {"actor_id":"original_chunk_npc:abc"},
            {"actor_id":False}, {"extra":1},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ChunkIndexError):
                    query_original_chunk_index(record,query=bad)

    def test_seeded_original_small_and_large_map_sources_preserve_body_identity(self):
        for chunks in (3,5):
            for seed in (0,1,7):
                with self.subTest(chunks=chunks,seed=seed):
                    game=source(people=32,chunks=chunks,seed=seed,
                                commands=["wait","move:west","move:east"])
                    report=build_original_chunk_index(game)
                    self.assertTrue(verify_original_chunk_index(report))
                    self.assertEqual(report["physical_actor_count"],32)
                    self.assertEqual(report["side"],7*chunks)
                    self.assertEqual(set(report["buckets"]),{
                        f"{cx}:{cy}" for cx in range(chunks)
                        for cy in range(chunks)})


class OriginalChunkIndexInterfaces(unittest.TestCase):
    def test_cli_source_and_query_round_trip_denies_forged_actor(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);s=root/"source.json";indexpath=root/"index.json"
            querypath=root/"query.json";save=root/"query-result.json"
            s.write_text(json.dumps(source(people=16,chunks=3)),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["index-original-npc-chunks","--record",str(s)]),0)
            index=json.loads(output.getvalue())
            indexpath.write_text(json.dumps(index),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-original-npc-chunks",
                                      "--record",str(indexpath)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            querypath.write_text(json.dumps({"center_chunk":[1,1],
                                             "radius":0,"limit":8}),
                                 encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["query-original-npc-chunks",
                     "--index",str(indexpath),"--query",str(querypath)]),0)
            record=json.loads(output.getvalue())
            self.assertEqual(record["schema"],QUERY_SCHEMA)
            save.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-original-npc-chunk-query",
                                      "--record",str(save)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            record["residents"][0]["position"]=0
            save.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-original-npc-chunk-query",
                                      "--record",str(save)]),2)

    def test_studio_uses_token_and_independently_replays_source_index(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_chunk_residency_index","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,data,authenticated=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=12)
                headers={"Content-Type":"application/json"}
                if authenticated:
                    headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(data),headers)
                res=conn.getresponse();code,body=res.status,json.loads(res.read())
                conn.close()
                return code,body
            try:
                game=source(people=16,chunks=3)
                self.assertEqual(post("/api/index-original-npc-chunks",
                                      {"record":game},False)[0],403)
                code,payload=post("/api/index-original-npc-chunks",{"record":game})
                self.assertEqual(code,200)
                self.assertTrue(payload["verified"])
                self.assertFalse(payload["source_files_mutated"])
                index=payload["index"]
                code,result=post("/api/query-original-npc-chunks",{
                    "index":index,"query":{"center_chunk":[1,1],"limit":8}})
                self.assertEqual(code,200)
                self.assertTrue(result["verified"])
                self.assertLessEqual(result["query"]["returned_count"],8)
                code,check=post("/api/verify-original-npc-chunk-query",{
                    "record":result["query"]})
                self.assertEqual(code,200)
                self.assertTrue(check["verified"])
                altered=deepcopy(index)
                altered["physical_actor_count"]=500
                self.assertEqual(post("/api/query-original-npc-chunks",{
                    "index":altered})[0],400)
                self.assertIn("Chunk Residency Index",
                              render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
