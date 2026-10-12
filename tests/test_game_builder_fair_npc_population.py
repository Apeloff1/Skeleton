"""Large original NPC populations and fair bounded simulation, no phantom LOD."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_chunked_npc_world import (
    ChunkWorldError, run_chunked_npc_world, verify_chunked_npc_world,
)
from skeleton.ai.game_builder.advanced_chunked_world_timeline import (
    make_chunked_bookmarks,continue_chunked_world,verify_chunked_continuation,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def rules(*, citizens=128, active=8, policy="fair", chunks=3, radius=1):
    return {"chunks_per_side":chunks,"citizens":citizens,"active_limit":active,
            "lod_policy":policy,"chunk_radius":radius,"max_turns":96}


class HigherCapacityNPCSimulationTests(unittest.TestCase):
    def test_one_hundred_twenty_eight_unique_physical_people_without_phantom_progress(self):
        for chunks in (3,5):
            with self.subTest(chunks=chunks):
                original=run_chunked_npc_world(["wait"]*6,
                                                options=rules(chunks=chunks))
                self.assertTrue(verify_chunked_npc_world(original))
                world=original["state"];actors=world["actors"]
                self.assertEqual(original["physical_actor_count"],128)
                self.assertEqual(len(actors),128)
                self.assertEqual(len({a["id"] for a in actors}),128)
                self.assertEqual(len({a["position"] for a in actors}),128)
                self.assertEqual(world["side"],7*chunks)
                self.assertLessEqual(world["scheduler"]["detailed_updates"],6*8)
                self.assertEqual(
                    world["scheduler"]["detailed_updates"]+
                    world["scheduler"]["deferred_actor_turns"],6*128)
                self.assertEqual(world["scheduler"]["forged_offscreen_events"],0)
                self.assertTrue(all(a["walked"]<=a["detailed_ticks"]
                                    for a in actors))
                self.assertTrue(all(a["deferred_ticks"]+a["detailed_ticks"]==6
                                    for a in actors))
                self.assertEqual(world["events"],[])
                self.assertEqual(world["quests"],[])
                self.assertFalse(original["gameplay_is_native_hardware_certified"])
                self.assertFalse(original["ai_model_weights_promoted"])
                self.assertEqual([a["id"] for a in actors],
                    ["original_chunk_npc:%03d"%i for i in range(128)])
                self.assertTrue(all(a["origin_kind"]==
                         "authored_quest_source_role" for a in actors[:4]))
                self.assertTrue(all(a["origin_kind"]==
                         "deterministic_original_generated_role" for a in actors[4:]))

    def test_fair_budget_cycles_through_more_real_citizens_than_nearest(self):
        base=["wait"]*24
        default=run_chunked_npc_world(base,options=rules(policy="nearest",citizens=64))
        fair=run_chunked_npc_world(base,options=rules(policy="fair",citizens=64))
        self.assertTrue(verify_chunked_npc_world(fair))
        self.assertTrue(verify_chunked_npc_world(default))
        nearest_served={a["id"] for a in default["state"]["actors"] if a["detailed_ticks"]}
        fair_served={a["id"] for a in fair["state"]["actors"] if a["detailed_ticks"]}
        self.assertGreater(len(fair_served),len(nearest_served))
        self.assertEqual(default["state"]["scheduler"]["detailed_updates"],
                         fair["state"]["scheduler"]["detailed_updates"])
        self.assertEqual(fair["state"]["scheduler"]["forged_offscreen_events"],0)
        self.assertGreater(fair["state"]["scheduler"]["eligible_deferred_actor_turns"],0)
        self.assertGreater(fair["state"]["scheduler"]["max_deferral_streak"],0)
        for citizen in fair["state"]["actors"]:
            self.assertLessEqual(citizen["longest_deferral"],24)
            self.assertGreaterEqual(citizen["eligible_deferred_ticks"],0)

    def test_window_fidelity_never_simulates_remote_residents(self):
        source=run_chunked_npc_world(["wait"]*12,
              options=rules(citizens=96,chunks=5,active=6,radius=0))
        self.assertTrue(verify_chunked_npc_world(source))
        state=source["state"]
        self.assertEqual(state["loaded_chunks"],[[2,2]])
        self.assertLessEqual(len(state["detailed_actor_ids"]),6)
        self.assertLessEqual(state["scheduler"]["detailed_updates"],12*6)
        self.assertTrue(any(a["deferred_ticks"]==12 for a in state["actors"]))
        self.assertEqual(state["scheduler"]["forged_offscreen_events"],0)
        self.assertFalse(state["dialogues"])
        self.assertFalse(state["quests"])
        self.assertFalse(state["events"])

    def test_lod_fairness_is_deterministic_and_all_actual_actor_moves_remain_adjacent(self):
        options=rules(citizens=96,active=16,chunks=5,radius=1)
        for seed in (0,1,7):
            original=run_chunked_npc_world(["wait"]*8,
                 seed=seed,options=options)
            repeat=run_chunked_npc_world(["wait"]*8,
                 seed=seed,options=options)
            self.assertEqual(original,repeat)
            self.assertTrue(verify_chunked_npc_world(original))
            side=original["state"]["side"]
            for frame in original["trace"]:
                self.assertLessEqual(len(frame["physical_moves"]),16)
                for move in frame["physical_moves"]:
                    a,b=move["from"],move["to"]
                    self.assertEqual(
                        abs(a%side-b%side)+abs(a//side-b//side),1)
                    self.assertTrue(move["one_tile"])

    def test_population_option_and_lod_policy_are_strict_typed(self):
        for bad in (
            {"citizens":129}, {"citizens":True}, {"citizens":7},
            {"citizens":"64"}, {"active_limit":33},
            {"active_limit":True}, {"active_limit":3},
            {"citizens":8,"active_limit":16},
            {"lod_policy":"unknown"}, {"lod_policy":True},
            {"lod_policy":0}, {"chunk_radius":2},
            {"unverified_population_rule":8},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ChunkWorldError):
                    run_chunked_npc_world([],options=bad)

    def test_fairness_and_actor_histories_cannot_be_forged_after_source_replay(self):
        record=run_chunked_npc_world(["wait"]*6,options=rules(citizens=64))
        for change in (
            lambda r:r["state"]["actors"][3].__setitem__("deferred_streak",100),
            lambda r:r["state"]["actors"][12].__setitem__("eligible_deferred_ticks",500),
            lambda r:r["state"]["scheduler"].__setitem__("eligible_deferred_actor_turns",0),
            lambda r:r["state"]["scheduler"].__setitem__("max_deferral_streak",0),
            lambda r:r["options"].__setitem__("lod_policy","nearest"),
            lambda r:r["options"].__setitem__("citizens",128),
            lambda r:r.__setitem__("physical_actor_count",128),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            altered=deepcopy(record);change(altered)
            with self.subTest(change=change):
                with self.assertRaises(ChunkWorldError):
                    verify_chunked_npc_world(altered)

    def test_source_bookmarks_and_real_fork_restore_physical_population(self):
        source=run_chunked_npc_world(["wait"]*8,
                 options=rules(citizens=64,active=8))
        checkpoint=make_chunked_bookmarks(source)
        branch=continue_chunked_world(checkpoint,
                                      ["move:west","move:east"],cursor=8)
        self.assertTrue(verify_chunked_continuation(branch))
        self.assertEqual(branch["result"]["physical_actor_count"],64)
        self.assertEqual(branch["result"]["options"]["lod_policy"],"fair")
        self.assertEqual(branch["result"]["state"]["tick"],10)
        self.assertEqual(branch["source_cursor_head"],source["head_digest"])


class PopulationEditorSurfaces(unittest.TestCase):
    def test_cli_64_actor_fair_population_can_be_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);options=root/"options.json";actions=root/"actions.json"
            saved=root/"saved.json"
            options.write_text(json.dumps(rules(citizens=64,active=8)),
                               encoding="utf-8")
            actions.write_text(json.dumps(["wait"]*4),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["chunked-npc-world","--actions",str(actions),
                                      "--options",str(options)]),0)
            record=json.loads(output.getvalue())
            self.assertEqual(record["physical_actor_count"],64)
            self.assertEqual(record["options"]["lod_policy"],"fair")
            saved.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-chunked-npc-world",
                                      "--record",str(saved)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})

    def test_studio_operator_auth_and_replay_cost_accounting(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_large_citizen_world","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,auth=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=12)
                headers={"Content-Type":"application/json"}
                if auth:headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),headers)
                res=conn.getresponse()
                code,content=res.status,json.loads(res.read())
                conn.close()
                return code,content
            try:
                packet={"actions":["wait"]*4,
                    "options":rules(citizens=64,active=8)}
                self.assertEqual(post("/api/chunked-npc-world",packet,False)[0],403)
                code,resp=post("/api/chunked-npc-world",packet)
                self.assertEqual(code,200)
                self.assertTrue(resp["independently_verified"])
                self.assertEqual(resp["record"]["physical_actor_count"],64)
                self.assertFalse(resp["source_files_mutated"])
                code,verify=post("/api/chunked-npc-world-verify",
                                  {"record":resp["record"]})
                self.assertEqual(code,200)
                self.assertTrue(verify["verified"])
                corrupt=deepcopy(resp["record"])
                corrupt["state"]["actors"][2]["deferred_streak"]+=2
                self.assertEqual(post("/api/chunked-npc-world-verify",
                                      {"record":corrupt})[0],400)
                html=render_workspace_html("x"*32).decode()
                self.assertIn("Balanced simulation",html)
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
