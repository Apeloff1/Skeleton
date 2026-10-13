"""Actual original NPC world positions, chronology and proof-backed time travel."""
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

from skeleton.ai.game_builder.advanced_historical_spatial_lens import (
    SCHEMA, ChunkIndexError,
    analyze_original_spatial_epochs, verify_original_spatial_epochs,
)
from skeleton.ai.game_builder.advanced_chunked_npc_world import (
    run_chunked_npc_world, verify_chunked_npc_world,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def game(*,seed=0,chunks=3,population=32):
    return run_chunked_npc_world(
        ["wait"]*7,seed=seed,options={
            "chunks_per_side":chunks,"citizens":population,
            "active_limit":8,"chunk_radius":1,"lod_policy":"fair",
        }
    )


class OriginalSpatialTimeLensTests(unittest.TestCase):
    def test_genesis_middle_and_final_chronology_matches_actual_original_source(self):
        source=game()
        proof=analyze_original_spatial_epochs(source,[0,3,7])
        self.assertTrue(verify_original_spatial_epochs(proof))
        self.assertEqual(proof["schema"],SCHEMA)
        self.assertEqual(proof["queried_original_turns"],[0,3,7])
        self.assertEqual(proof["historical_epoch_count"],3)
        self.assertEqual(proof["source_game_digest"],source["digest"])
        self.assertEqual(proof["epochs"][-1]["actual_source_head"],source["head_digest"])
        self.assertEqual(proof["epochs"][0]["turn"],0)
        self.assertEqual(proof["epochs"][0]["real_one_tile_moves_in_interval"],0)
        self.assertEqual(proof["epochs"][0]["detailed_update_count"],0)
        self.assertEqual(proof["epochs"][1]["detailed_update_count"]+
                         proof["epochs"][1]["deferred_actor_turns"],3*32)
        self.assertEqual(proof["epochs"][2]["detailed_update_count"]+
                         proof["epochs"][2]["deferred_actor_turns"],7*32)
        self.assertEqual(proof["epochs"][-1]["all_unique_original_actor_positions"],{
            x["id"]:x["position"] for x in source["state"]["actors"]
        })
        self.assertTrue(proof["source_transitions_are_real_not_interpolated"])
        self.assertTrue(proof["full_origin_source_replay_verified"])
        self.assertFalse(proof["native_engine_certified"])
        self.assertFalse(proof["model_weights_promoted"])
        self.assertFalse(proof["original_game_files_changed"])

    def test_changed_actor_list_only_uses_actual_action_frame_movement(self):
        source=game(population=64)
        record=analyze_original_spatial_epochs(source,[0,2,4,7])
        self.assertTrue(verify_original_spatial_epochs(record))
        for i,epoch in enumerate(record["epochs"][1:],1):
            previous=record["epochs"][i-1]
            before=previous["all_unique_original_actor_positions"]
            after=epoch["all_unique_original_actor_positions"]
            self.assertEqual(set(before),set(after))
            delta={name for name in after if before[name]!=after[name]}
            self.assertEqual(set(epoch["changed_body_ids_since_previous_epoch"]),delta)
            self.assertGreaterEqual(epoch["real_one_tile_moves_in_interval"],len(delta))
            self.assertEqual(sum(epoch["chunk_occupancy"].values()),64)
        self.assertEqual(record["epochs"][-1]["real_one_tile_moves_in_interval"],
                         sum(len(f["physical_moves"])
                             for f in source["trace"][4:7]))

    def test_bounded_chunk_history_reports_genuine_source_neighborhood(self):
        source=game(population=64,chunks=5)
        q={"center_chunk":[0,0],"radius":0,"limit":12}
        record=analyze_original_spatial_epochs(source,[0,3,7],query=q)
        self.assertTrue(verify_original_spatial_epochs(record))
        for epoch in record["epochs"]:
            view=epoch["query"]
            self.assertEqual(view["candidate_chunk_keys"],["0:0"])
            self.assertLess(view["candidate_actor_entries_examined"],64)
            self.assertLessEqual(view["returned_count"],12)
            for citizen in view["residents"]:
                x=citizen["position"]%35
                y=citizen["position"]//35
                self.assertEqual([x//7,y//7],[0,0])
                self.assertEqual(citizen["source_head"],epoch["actual_source_head"])

    def test_128_unique_citizens_remain_physical_across_selected_original_epochs(self):
        for seed in (0,5):
            source=game(seed=seed,chunks=5,population=128)
            timeline=analyze_original_spatial_epochs(source,[0,4,7])
            with self.subTest(seed=seed):
                self.assertTrue(verify_original_spatial_epochs(timeline))
                for epoch in timeline["epochs"]:
                    identities=epoch["all_unique_original_actor_positions"]
                    self.assertEqual(len(identities),128)
                    self.assertEqual(len(set(identities.values())),128)
                    self.assertEqual(sum(epoch["chunk_occupancy"].values()),128)
                    self.assertNotIn(epoch["player_position"],set(identities.values()))
                    self.assertEqual(epoch["physical_actor_count"],128)

    def test_empty_original_game_allows_only_genesis(self):
        source=run_chunked_npc_world([])
        record=analyze_original_spatial_epochs(source,[0])
        self.assertTrue(verify_original_spatial_epochs(record))
        self.assertEqual(record["epochs"][0]["actual_source_head"],
                         source["head_digest"])
        self.assertEqual(record["extra_prefix_transitions_replayed_during_index_build"],0)
        with self.assertRaises(ChunkIndexError):
            analyze_original_spatial_epochs(source,[1])

    def test_epoch_input_is_strict_increasing_bounded_non_boolean(self):
        source=game()
        for turns in (
            [],[False],[True],[0,0],[3,1],[7,8],[-1],
            [1.0],["3"],list(range(13)),None,
        ):
            with self.subTest(turns=turns):
                with self.assertRaises(ChunkIndexError):
                    analyze_original_spatial_epochs(source,turns)
        with self.assertRaises(ChunkIndexError):
            analyze_original_spatial_epochs(source,[0,1],query={"radius":2})

    def test_altered_historical_actor_body_and_ledger_fails_closed(self):
        original=analyze_original_spatial_epochs(game(),[0,3,7])
        for attack in (
            lambda r:r["epochs"][1]["all_unique_original_actor_positions"].__setitem__(
                "original_chunk_npc:000",999),
            lambda r:r["epochs"][2]["chunk_occupancy"].__setitem__("1:1",100),
            lambda r:r["epochs"][1].__setitem__("real_one_tile_moves_in_interval",100),
            lambda r:r["epochs"][0].__setitem__("actual_source_head","0"*64),
            lambda r:r["epochs"][2]["query"].__setitem__("candidate_actor_entries_examined",0),
            lambda r:r["source_game"]["state"]["scheduler"].__setitem__(
                "deferred_actor_turns",999),
            lambda r:r.__setitem__("native_engine_certified",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            damaged=deepcopy(original);attack(damaged)
            with self.subTest(attack=attack):
                with self.assertRaises(ChunkIndexError):
                    verify_original_spatial_epochs(damaged)

    def test_true_original_source_seed_and_settings_change_historical_digest(self):
        a=analyze_original_spatial_epochs(game(seed=0),[0,4,7])
        b=analyze_original_spatial_epochs(game(seed=1),[0,4,7])
        self.assertTrue(verify_original_spatial_epochs(a))
        self.assertTrue(verify_original_spatial_epochs(b))
        self.assertNotEqual(a["digest"],b["digest"])
        self.assertNotEqual(a["source_game_digest"],b["source_game_digest"])


class OriginalSpatialHistoryInterfaces(unittest.TestCase):
    def test_cli_reconstructs_historical_original_world_with_strict_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);s=base/"source.json";t=base/"turns.json"
            q=base/"query.json";output=base/"history.json"
            s.write_text(json.dumps(game()),encoding="utf-8")
            t.write_text(json.dumps([0,3,7]),encoding="utf-8")
            q.write_text(json.dumps({"center_chunk":[1,1],"radius":0,
                                     "limit":8}),encoding="utf-8")
            with redirect_stdout(StringIO()) as buffer:
                self.assertEqual(cli(["original-spatial-history","--record",str(s),
                                      "--turns",str(t),"--query",str(q)]),0)
            record=json.loads(buffer.getvalue())
            self.assertEqual(record["historical_epoch_count"],3)
            output.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stdout(StringIO()) as buffer:
                self.assertEqual(cli(["verify-original-spatial-history",
                                      "--record",str(output)]),0)
            self.assertEqual(json.loads(buffer.getvalue()),{"verified":True})
            record["epochs"][1]["player_position"]=900
            output.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-original-spatial-history",
                                      "--record",str(output)]),2)

    def test_studio_token_required_for_source_historical_playback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=GameWorkspace.create(Path(tmp)/"studio",authorized=True)
            ws.create_project("source_verified_spatial_history","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(url,data,authorized=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=15)
                h={"Content-Type":"application/json"}
                if authorized:h["X-Game-Studio-Token"]=server.secret
                conn.request("POST",url,json.dumps(data),h)
                res=conn.getresponse();code,body=res.status,json.loads(res.read())
                conn.close()
                return code,body
            try:
                source=game()
                packet={"record":source,"turns":[0,3,7],
                        "query":{"center_chunk":[1,1],"radius":0,"limit":8}}
                self.assertEqual(post("/api/original-spatial-history",packet,False)[0],403)
                code,payload=post("/api/original-spatial-history",packet)
                self.assertEqual(code,200)
                self.assertTrue(payload["verified"])
                self.assertFalse(payload["source_files_mutated"])
                history=payload["record"]
                self.assertEqual(history["historical_epoch_count"],3)
                code,checked=post("/api/verify-original-spatial-history",
                                  {"record":history})
                self.assertEqual(code,200)
                self.assertTrue(checked["verified"])
                forged=deepcopy(history)
                forged["epochs"][0]["all_unique_original_actor_positions"][
                    "original_chunk_npc:000"]=700
                self.assertEqual(post("/api/verify-original-spatial-history",
                                      {"record":forged})[0],400)
                self.assertIn("Historical Spatial Lens",
                              render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
