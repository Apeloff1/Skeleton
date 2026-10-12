"""Source-authenticated original chunked game save bookmarks and timeline forks."""
from __future__ import annotations

from contextlib import redirect_stderr,redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_chunked_npc_world import (
    run_chunked_npc_world,verify_chunked_npc_world,
)
from skeleton.ai.game_builder.advanced_chunked_world_timeline import (
    SCHEMA,BRANCH_SCHEMA,ChunkTimelineError,
    make_chunked_bookmarks,verify_chunked_bookmarks,
    continue_chunked_world,verify_chunked_continuation,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class OriginalStreamingTimelineTests(unittest.TestCase):
    def test_real_original_turn_bookmarks_bind_actual_action_receipt_heads(self):
        original=run_chunked_npc_world(["wait"]*16)
        record=make_chunked_bookmarks(original,interval=8)
        self.assertTrue(verify_chunked_bookmarks(record))
        self.assertEqual(record["schema"],SCHEMA)
        self.assertEqual([p["cursor"] for p in record["bookmarks"]],[0,8,16])
        self.assertEqual(record["bookmarks"][0]["action_head"],
                         original["trace"][0]["previous"])
        for point in record["bookmarks"][1:]:
            frame=original["trace"][point["cursor"]-1]
            self.assertEqual(point["action_head"],frame["digest"])
            self.assertEqual(point["result_state_digest"],frame["after"])
        self.assertEqual(record["source_actor_count"],16)
        self.assertEqual(record["source_world_digest"],original["digest"])
        self.assertFalse(record["model_weights_promoted"])
        self.assertFalse(record["source_project_mutated"])
        self.assertFalse(record["native_restore_speed_certified"])

    def test_fork_is_a_real_new_original_history_not_a_state_swap(self):
        previous=run_chunked_npc_world(["wait"]*16,
                                        options={"chunks_per_side":3,
                                                 "citizens":24,
                                                 "active_limit":8})
        original=make_chunked_bookmarks(previous)
        branch=continue_chunked_world(
            original,["move:west","move:east","wait"],cursor=8)
        self.assertTrue(verify_chunked_continuation(branch))
        self.assertEqual(branch["schema"],BRANCH_SCHEMA)
        self.assertEqual(branch["cursor"],8)
        self.assertEqual(branch["result"]["commands"],
                         ["wait"]*8+["move:west","move:east","wait"])
        self.assertEqual(branch["discarded_future_actions"],["wait"]*8)
        self.assertEqual(len(branch["result"]["trace"]),11)
        self.assertEqual(branch["result"]["head_digest"],
                         branch["result"]["trace"][-1]["digest"])
        self.assertNotEqual(branch["result_world_digest"],previous["digest"])
        self.assertEqual(branch["source_cursor_head"],
                         previous["trace"][7]["digest"])
        self.assertFalse(branch["incremental_snapshot_restore_claimed"])
        self.assertFalse(branch["source_files_modified"])
        self.assertFalse(branch["ai_model_weights_promoted"])
        self.assertTrue(verify_chunked_npc_world(branch["result"]))

    def test_continuation_from_final_cursor_is_a_real_appended_game(self):
        source=run_chunked_npc_world(["wait"]*8)
        checkpoint=make_chunked_bookmarks(source)
        later=continue_chunked_world(checkpoint,["move:west","move:east"])
        self.assertTrue(verify_chunked_continuation(later))
        self.assertEqual(later["cursor"],8)
        self.assertEqual(later["discarded_future_actions"],[])
        self.assertEqual(later["result"]["state"]["tick"],10)
        self.assertEqual(later["result"]["commands"],
                         ["wait"]*8+["move:west","move:east"])
        self.assertEqual(later["result"]["seed"],source["seed"])

    def test_end_cursor_and_genesis_are_valid_even_for_empty_game(self):
        source=run_chunked_npc_world([])
        checkpoint=make_chunked_bookmarks(source)
        self.assertEqual(len(checkpoint["bookmarks"]),1)
        self.assertEqual(checkpoint["bookmarks"][0]["cursor"],0)
        self.assertIsNone(checkpoint["bookmarks"][0]["result_state_digest"])
        self.assertTrue(verify_chunked_bookmarks(checkpoint))
        after=continue_chunked_world(checkpoint,["wait"])
        self.assertTrue(verify_chunked_continuation(after))
        self.assertEqual(after["result"]["state"]["tick"],1)

    def test_seeds_and_larger_worlds_retained_through_forks(self):
        for seed in (0,1,5,9):
            options={"chunks_per_side":5,"citizens":32,
                     "active_limit":6,"chunk_radius":0}
            original=run_chunked_npc_world(["wait"]*8,
                                            options=options,seed=seed)
            book=make_chunked_bookmarks(original)
            fork=continue_chunked_world(book,["wait","move:west"],cursor=8)
            with self.subTest(seed=seed):
                self.assertTrue(verify_chunked_continuation(fork))
                self.assertEqual(fork["result"]["state"]["side"],35)
                self.assertEqual(fork["result"]["physical_actor_count"],32)
                self.assertEqual(fork["result"]["seed"],seed)
                self.assertEqual(fork["result"]["options"],original["options"])
                self.assertEqual(fork["result"]["source_identities"],
                                 original["source_identities"])

    def test_forged_origins_bookmarks_receipt_heads_and_results_fail_closed(self):
        original=make_chunked_bookmarks(run_chunked_npc_world(["wait"]*8))
        branch=continue_chunked_world(original,["move:west"])
        for attack in (
            lambda r:r["bookmarks"][1].__setitem__("action_head","0"*64),
            lambda r:r["source_world"]["state"]["actors"][0].__setitem__("position",44),
            lambda r:r["bookmarks"][0].__setitem__("result_state_digest","x"*64),
            lambda r:r.__setitem__("native_restore_speed_certified",True),
            lambda r:r.__setitem__("source_world_digest","a"*64),
            lambda r:r.__setitem__("digest","b"*64),
        ):
            corrupted=deepcopy(original)
            attack(corrupted)
            with self.subTest(checkpoint=attack):
                with self.assertRaises(ChunkTimelineError):
                    verify_chunked_bookmarks(corrupted)
        for attack in (
            lambda r:r["result"]["state"]["inventory"].__setitem__("supplies",999),
            lambda r:r.__setitem__("source_cursor_head","0"*64),
            lambda r:r["source_checkpoint"]["bookmarks"][1].__setitem__("cursor",7),
            lambda r:r["appended_actions"].append("harvest:0"),
            lambda r:r.__setitem__("ai_model_weights_promoted",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            corrupted=deepcopy(branch)
            attack(corrupted)
            with self.subTest(branch=attack):
                with self.assertRaises(ChunkTimelineError):
                    verify_chunked_continuation(corrupted)

    def test_invalid_fork_positions_and_illegal_actions_are_refused(self):
        original=make_chunked_bookmarks(run_chunked_npc_world(["wait"]*16))
        for bad in (
            {"cursor":7}, {"cursor":True}, {"cursor":-1},
            {"cursor":17}, {"cursor":"8"},
        ):
            with self.subTest(cursor=bad):
                with self.assertRaises(ChunkTimelineError):
                    continue_chunked_world(original,["wait"],**bad)
        for commands in ("wait",[False],["teleport:5"],[""],["wait"]*129):
            with self.subTest(commands=commands):
                with self.assertRaises(ChunkTimelineError):
                    continue_chunked_world(original,commands)
        for interval in (0,7,65,True,"8"):
            with self.subTest(interval=interval):
                with self.assertRaises(ChunkTimelineError):
                    make_chunked_bookmarks(original["source_world"],
                                          interval=interval)


class ChunkTimelineSurfaces(unittest.TestCase):
    def test_offline_cli_can_bookmark_verify_fork_and_check_new_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"source.json";book=root/"book.json";steps=root/"suffix.json"
            saved=root/"branch.json"
            source.write_text(json.dumps(run_chunked_npc_world(["wait"]*8)),encoding="utf-8")
            steps.write_text(json.dumps(["move:west","move:east"]),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["chunked-world-checkpoint",
                                      "--record",str(source)]),0)
            checkpoint=json.loads(output.getvalue())
            self.assertEqual(checkpoint["schema"],SCHEMA)
            book.write_text(json.dumps(checkpoint),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-chunked-world-checkpoint",
                                      "--record",str(book)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["chunked-world-continue",
                                      "--checkpoint",str(book),
                                      "--actions",str(steps)]),0)
            branch=json.loads(output.getvalue())
            self.assertEqual(branch["result"]["state"]["tick"],10)
            saved.write_text(json.dumps(branch),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-chunked-world-continuation",
                                      "--record",str(saved)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            branch["result"]["state"]["actors"][0]["trust"]+=50
            saved.write_text(json.dumps(branch),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-chunked-world-continuation",
                                      "--record",str(saved)]),2)

    def test_studio_requires_token_and_replay_proof_for_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            ws=GameWorkspace.create(Path(folder)/"studio",authorized=True)
            ws.create_project("historic_original_world","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,authenticated=True):
                client=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=12)
                headers={"Content-Type":"application/json"}
                if authenticated:
                    headers["X-Game-Studio-Token"]=server.secret
                client.request("POST",path,json.dumps(body),headers)
                response=client.getresponse()
                code,raw=response.status,response.read()
                client.close()
                return code,json.loads(raw)
            try:
                source=run_chunked_npc_world(["wait"]*8)
                payload={"record":source}
                self.assertEqual(post("/api/chunked-world-checkpoint",payload,False)[0],403)
                code,response=post("/api/chunked-world-checkpoint",payload)
                self.assertEqual(code,200)
                self.assertTrue(response["verified"])
                checkpoint=response["checkpoint"]
                code,response=post("/api/chunked-world-continue",{
                    "checkpoint":checkpoint,"actions":["move:west"]
                })
                self.assertEqual(code,200)
                self.assertTrue(response["verified"])
                branch=response["branch"]
                self.assertEqual(branch["result"]["state"]["tick"],9)
                code,checked=post("/api/chunked-world-continuation-verify",{
                    "record":branch
                })
                self.assertEqual(code,200)
                self.assertTrue(checked["verified"])
                forged=deepcopy(branch)
                forged["result"]["state"]["completed"]=44
                self.assertEqual(post("/api/chunked-world-continuation-verify",{
                    "record":forged
                })[0],400)
                html=render_workspace_html("x"*32).decode()
                self.assertIn("Streaming Timeline",html)
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
