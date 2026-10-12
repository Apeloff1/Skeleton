"""Fast trusted NPC snapshots: exact parity, security boundaries and surfaces."""
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

from skeleton.ai.game_builder.advanced_chunked_npc_world import (
    run_chunked_npc_world, verify_chunked_npc_world,
)
from skeleton.ai.game_builder.advanced_chunked_world_timeline import (
    make_chunked_bookmarks, continue_chunked_world,
    verify_chunked_continuation, ChunkTimelineError,
)
from skeleton.ai.game_builder.advanced_fast_chunk_snapshot import (
    MAX_BRANCHES, SCHEMA, prepare_verified_chunk_snapshot,
    run_fast_chunk_branches, verify_fast_chunk_branches,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def checkpoint(*, seed=0, options=None):
    return make_chunked_bookmarks(run_chunked_npc_world(
        ["wait"]*16, seed=seed, options=options
    ), interval=8)


class OriginalVerifiedFastSnapshotTests(unittest.TestCase):
    def test_exact_full_receipt_matches_from_genesis_on_all_three_bookmarks(self):
        original=checkpoint()
        for cursor in (0,8,16):
            with self.subTest(cursor=cursor):
                prepared=prepare_verified_chunk_snapshot(original,cursor=cursor)
                self.assertEqual(prepared.cursor,cursor)
                self.assertEqual(prepared.actor_count,16)
                for suffix in ([],["wait"],["move:west","move:east"]):
                    fast=prepared.fork(suffix)
                    slow=continue_chunked_world(original,suffix,cursor=cursor)
                    self.assertEqual(fast,slow)
                    self.assertTrue(verify_chunked_continuation(fast))
                    self.assertEqual(fast["result"]["head_digest"],
                                     slow["result"]["head_digest"])
                    self.assertEqual(fast["result"]["state"],slow["result"]["state"])

    def test_trusted_preparation_reused_without_leaking_mutable_actor_snapshots(self):
        prior=checkpoint()
        prepared=prepare_verified_chunk_snapshot(prior,cursor=8)
        a=prepared.fork(["move:west"])
        a["result"]["state"]["actors"][0]["trust"]=9999
        b=prepared.fork(["move:west"])
        expected=continue_chunked_world(prior,["move:west"],cursor=8)
        self.assertEqual(b,expected)
        self.assertNotEqual(a,b)
        self.assertTrue(verify_chunked_continuation(b))
        divergent=prepared.fork(["move:east"])
        self.assertNotEqual(divergent["result_world_digest"],
                            b["result_world_digest"])
        self.assertEqual(prepared.cursor,8)

    def test_replay_parity_remains_true_with_different_world_sizes_and_cohorts(self):
        for seed in (0,1,5):
            for side in (3,5):
                with self.subTest(seed=seed,chunks=side):
                    original=checkpoint(seed=seed,options={
                        "chunks_per_side":side,"citizens":32,
                        "active_limit":6,"chunk_radius":0})
                    prepared=prepare_verified_chunk_snapshot(original,cursor=8)
                    for suffix in (["wait"],["move:west","move:east"]):
                        self.assertEqual(
                            prepared.fork(suffix),
                            continue_chunked_world(original,suffix,cursor=8))

    def test_branch_batch_has_exact_replayable_results_without_duplicate_world_blobs(self):
        source=checkpoint()
        variants=[
            {"name":"west_walk","actions":["move:west","wait"]},
            {"name":"east_walk","actions":["move:east","wait"]},
            {"name":"stationary","actions":["wait","wait"]},
        ]
        report=run_fast_chunk_branches(source,variants,cursor=8)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["original_prefix_authentications"],1)
        self.assertEqual(report["suffix_transitions_executed"],6)
        self.assertEqual(report["prefix_transitions_reexecuted_during_branch_forks"],0)
        self.assertTrue(report["full_replay_used_during_preparation"])
        self.assertFalse(report["native_speed_certified"])
        self.assertFalse(report["core_model_weights_promoted"])
        self.assertEqual(len(report["results"]),3)
        self.assertTrue(all("complete_branch" not in item for item in report["results"]))
        self.assertTrue(verify_fast_chunk_branches(report))
        for variant,item in zip(variants,report["results"]):
            original=continue_chunked_world(source,variant["actions"],cursor=8)
            self.assertEqual(item["result_digest"],original["result_world_digest"])
            self.assertEqual(item["result_head"],original["result"]["head_digest"])

    def test_untrusted_modified_parent_checkpoint_never_opens_fast_path(self):
        base=checkpoint()
        for corruption in (
            lambda r:r["bookmarks"][1].__setitem__("action_head","0"*64),
            lambda r:r["source_world"]["state"]["actors"][0].__setitem__("position",999),
            lambda r:r["source_world"].__setitem__("head_digest","a"*64),
            lambda r:r.__setitem__("digest","f"*64),
        ):
            forged=deepcopy(base)
            corruption(forged)
            with self.subTest(corruption=corruption):
                with self.assertRaises(ChunkTimelineError):
                    prepare_verified_chunk_snapshot(forged,cursor=8)

    def test_bad_continuations_and_cursors_refuse_to_mutate_cached_state(self):
        source=checkpoint()
        for cursor in (-1,2,7,17,True,"8"):
            with self.subTest(cursor=cursor):
                with self.assertRaises(ChunkTimelineError):
                    prepare_verified_chunk_snapshot(source,cursor=cursor)
        prepared=prepare_verified_chunk_snapshot(source,cursor=8)
        for suffix in (["move:up"],[None],[""],["wait"]*129,"wait"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(ChunkTimelineError):
                    prepared.fork(suffix)
        self.assertEqual(prepared.fork(["wait"]),
                         continue_chunked_world(source,["wait"],cursor=8))

    def test_batch_rejects_duplicate_names_bad_schema_and_excessive_branches(self):
        source=checkpoint()
        for variants in (
            [],[{"name":"invalid name","actions":[]}],
            [{"name":"a","actions":[]},{"name":"a","actions":[]}],
            [{"name":"one","actions":"wait"}],
            [{"name":"a","actions":[],"rogue":True}],
            [{"name":"bad","actions":[]}]* (MAX_BRANCHES+1),
            [None],
        ):
            with self.subTest(variants=variants):
                with self.assertRaises(ChunkTimelineError):
                    run_fast_chunk_branches(source,variants,cursor=8)

    def test_forged_fast_multi_branch_outputs_fail_full_source_verifier(self):
        base=run_fast_chunk_branches(checkpoint(),
            [{"name":"a","actions":["wait"]},
             {"name":"b","actions":["move:west"]}],cursor=8)
        for change in (
            lambda r:r["results"][0]["state"].__setitem__("supplies",99999),
            lambda r:r["results"][0].__setitem__("result_head","0"*64),
            lambda r:r["results"][1]["appended_actions"].append("move:east"),
            lambda r:r.__setitem__("prefix_transitions_reexecuted_during_branch_forks",5),
            lambda r:r.__setitem__("core_model_weights_promoted",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            forged=deepcopy(base);change(forged)
            with self.subTest(change=change):
                with self.assertRaises(ChunkTimelineError):
                    verify_fast_chunk_branches(forged)

    def test_one_actor_game_retirement_replay_can_match_real_material_story(self):
        original=make_chunked_bookmarks(run_chunked_npc_world([]))
        story=["move:south","move:east","harvest:0","speak:0","support:0",
               *["repair:0"]*5,"claim:0"]
        prepared=prepare_verified_chunk_snapshot(original)
        fast=prepared.fork(story)
        slow=continue_chunked_world(original,story)
        self.assertEqual(fast,slow)
        self.assertEqual(fast["result"]["state"]["completed"],1)
        self.assertTrue(verify_chunked_continuation(fast))


class OriginalFastSnapshotSurfaces(unittest.TestCase):
    def test_cli_batch_and_full_replay_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a=root/"checkpoint.json";b=root/"branches.json";out=root/"result.json"
            a.write_text(json.dumps(checkpoint()),encoding="utf-8")
            b.write_text(json.dumps([{"name":"west","actions":["move:west"]}]),
                         encoding="utf-8")
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(cli(["fast-chunk-forks",
                                      "--checkpoint",str(a),
                                      "--branches",str(b),"--cursor","8"]),0)
            result=json.loads(captured.getvalue())
            self.assertEqual(result["original_prefix_authentications"],1)
            self.assertEqual(result["results"][0]["name"],"west")
            out.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(cli(["verify-fast-chunk-forks",
                                      "--record",str(out)]),0)
            self.assertEqual(json.loads(captured.getvalue()),{"verified":True})
            result["results"][0]["result_digest"]="0"*64
            out.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-fast-chunk-forks",
                                      "--record",str(out)]),2)

    def test_authenticated_studio_never_accepts_forged_fork_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_fast_fork_batch","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,authorized=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=12)
                headers={"Content-Type":"application/json"}
                if authorized: headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),headers)
                response=conn.getresponse()
                status,content=response.status,json.loads(response.read())
                conn.close()
                return status,content
            try:
                content={"checkpoint":checkpoint(),"cursor":8,
                         "branches":[{"name":"walk","actions":["move:west"]}]}
                self.assertEqual(post("/api/fast-chunk-forks",content,False)[0],403)
                code,response=post("/api/fast-chunk-forks",content)
                self.assertEqual(code,200)
                self.assertTrue(response["verified"])
                self.assertFalse(response["source_files_mutated"])
                self.assertFalse(response["speed_certified"])
                batch=response["record"]
                code,check=post("/api/fast-chunk-forks-verify",{"record":batch})
                self.assertEqual(code,200)
                self.assertTrue(check["verified"])
                forged=deepcopy(batch)
                forged["results"][0]["result_head"]="0"*64
                self.assertEqual(post("/api/fast-chunk-forks-verify",
                                      {"record":forged})[0],400)
                self.assertIn("Fast Branch Lab",render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
