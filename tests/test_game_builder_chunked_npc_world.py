"""Original multi-chunk NPC world: physical streaming, bounded LOD and replay."""
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
    CHUNK_EDGE, SCHEMA, DEFAULTS, PHASES, ChunkWorldError,
    run_chunked_npc_world, verify_chunked_npc_world,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html

STORY = ["move:south","move:east","harvest:0","speak:0","support:0",
         *["repair:0"]*5,"claim:0"]


class ChunkedNPCTest(unittest.TestCase):
    def test_three_by_three_world_has_sixteen_real_persistent_original_ids(self):
        source=run_chunked_npc_world([])
        self.assertTrue(verify_chunked_npc_world(source))
        state=source["state"]
        self.assertEqual(state["side"],21)
        self.assertEqual(state["chunks_per_side"],3)
        self.assertEqual(state["chunk_size"],CHUNK_EDGE)
        self.assertEqual(source["physical_actor_count"],16)
        self.assertEqual(len(state["actors"]),16)
        self.assertEqual(len({a["id"] for a in state["actors"]}),16)
        self.assertEqual(len({a["position"] for a in state["actors"]}),16)
        self.assertEqual(state["scheduler"]["forged_offscreen_events"],0)
        self.assertTrue(source["offscreen_movement_was_not_fabricated"])
        self.assertFalse(source["gameplay_is_native_hardware_certified"])
        self.assertFalse(source["source_files_mutated"])
        self.assertFalse(source["ai_model_weights_promoted"])
        for i,a in enumerate(state["actors"]):
            self.assertEqual(a["index"],i)
            self.assertEqual(a["id"],"original_chunk_npc:%03d"%i)
            self.assertEqual(a["walked"],0)
            self.assertEqual(a["deferred_ticks"],0)
        for a in state["actors"][:4]:
            self.assertEqual(a["origin_kind"],"authored_quest_source_role")
        for a in state["actors"][4:]:
            self.assertEqual(a["origin_kind"],"deterministic_original_generated_role")

    def test_five_by_five_world_has_stable_thirty_two_ids_and_bounded_updates(self):
        options={"chunks_per_side":5,"citizens":32,"active_limit":6,
                 "chunk_radius":0}
        record=run_chunked_npc_world(["wait"]*8,options=options)
        self.assertEqual(record["state"]["side"],35)
        self.assertEqual(record["physical_actor_count"],32)
        self.assertTrue(verify_chunked_npc_world(record))
        state=record["state"]
        self.assertLessEqual(state["scheduler"]["detailed_updates"],8*6)
        self.assertEqual(state["scheduler"]["deferred_actor_turns"]+
                         state["scheduler"]["detailed_updates"],8*32)
        self.assertEqual(len(state["loaded_chunks"]),1)
        self.assertEqual(state["loaded_chunks"],[[2,2]])
        self.assertLessEqual(len(state["detailed_actor_ids"]),6)
        self.assertEqual(state["scheduler"]["forged_offscreen_events"],0)
        for actor in state["actors"]:
            self.assertEqual(actor["detailed_ticks"]+actor["deferred_ticks"],8)
            self.assertEqual(actor["id"],
                             "original_chunk_npc:%03d"%actor["index"])
            self.assertLessEqual(actor["walked"],actor["detailed_ticks"])
        self.assertTrue(any(a["deferred_ticks"]==8 for a in state["actors"]))
        self.assertEqual(len({a["position"] for a in state["actors"]}),32)

    def test_chunks_are_connected_and_camera_moves_without_world_teleportation(self):
        options={"chunks_per_side":3,"citizens":16,"active_limit":4,
                 "chunk_radius":0}
        record=run_chunked_npc_world(["move:west","move:east"],options=options)
        self.assertTrue(verify_chunked_npc_world(record))
        state=record["state"]
        self.assertEqual(state["side"],21)
        self.assertEqual(state["player"],7+7*21)
        self.assertEqual(state["loaded_chunks"],[[1,1]])
        self.assertEqual(len(record["trace"]),2)
        self.assertEqual(record["trace"][0]["command"],"move:west")
        self.assertEqual(record["trace"][0]["tick"],1)
        self.assertEqual(record["trace"][1]["tick"],2)
        self.assertTrue(all(row["ordered_phases"]==list(PHASES)
                            for row in record["trace"]))
        self.assertNotEqual(record["trace"][0]["after"],
                            record["trace"][1]["after"])

    def test_real_witnessed_story_requires_material_and_dialogue(self):
        record=run_chunked_npc_world(STORY)
        self.assertTrue(verify_chunked_npc_world(record))
        state=record["state"]
        self.assertEqual(state["completed"],1)
        self.assertEqual(state["quests"][0]["status"],"resolved")
        self.assertEqual(state["quests"][0]["ending"],"restored")
        self.assertEqual(state["quests"][0]["followups"],5)
        self.assertIn(0,state["events"][0]["direct_witnesses"])
        self.assertEqual(state["dialogues"][0]["source"],
                         "firsthand_physical_witness")
        self.assertEqual(state["dialogues"][0]["event_id"],0)
        self.assertEqual(state["choices"][0]["actor"],
                         "original_chunk_npc:000")
        self.assertEqual(state["choices"][0]["material_cost"],1)
        self.assertFalse(state["finished"])
        self.assertTrue(verify_chunked_npc_world(
            run_chunked_npc_world([*STORY,"retire"])
        ))

    def test_nonterminal_observation_never_mints_gold_or_distant_testimony(self):
        record=run_chunked_npc_world(["wait"]*12,
                                      options={"chunks_per_side":5,
                                               "active_limit":4})
        self.assertTrue(verify_chunked_npc_world(record))
        state=record["state"]
        self.assertEqual(state["events"],[])
        self.assertEqual(state["quests"],[])
        self.assertEqual(state["dialogues"],[])
        self.assertEqual(state["choices"],[])
        self.assertFalse(state["finished"])
        self.assertEqual(state["completed"],0)
        self.assertEqual(state["scheduler"]["forged_offscreen_events"],0)
        self.assertLessEqual(state["scheduler"]["detailed_updates"],12*4)
        self.assertEqual(state["scheduler"]["deferred_actor_turns"]+
                         state["scheduler"]["detailed_updates"],
                         12*DEFAULTS["citizens"])

    def test_invalid_actions_remote_sources_and_finite_material_are_rejected(self):
        bad=(
            ["speak:31"],["support:0"],["repair:0"],["claim:0"],
            ["harvest:0"],["move:up"],["move:northeast"],
            ["move:west"]*9,["move:north"]*9,
            ["move:south","move:east","harvest:0","support:0"],
            ["move:south","move:east","harvest:0","speak:0","claim:0"],
            ["retire"],[None],[""],["inspect"]*129,
        )
        for actions in bad:
            with self.subTest(actions=actions):
                with self.assertRaises(ChunkWorldError):
                    run_chunked_npc_world(actions)

    def test_expanded_thirty_three_citizens_is_now_valid_original_gameplay(self):
        # The previous 32-citizen cap no longer holds; 33 is a supported,
        # physically embodied source population, whereas 129 is not.
        report=run_chunked_npc_world(["wait"],options={
            "citizens":33,"active_limit":8,
        })
        self.assertEqual(report["physical_actor_count"],33)
        self.assertTrue(verify_chunked_npc_world(report))

    def test_wrong_types_and_budgets_rejected_before_source(self):
        cases=(
            {"options":{"chunks_per_side":4}},
            {"options":{"chunks_per_side":True}},
            {"options":{"citizens":129}},
            {"options":{"citizens":8,"active_limit":9}},
            {"options":{"active_limit":0}},
            {"options":{"chunk_radius":2}},
            {"options":{"max_turns":0}},
            {"options":{"active_limit":"8"}},
            {"options":{"evil_option":1}},
            {"seed":True},{"seed":-1},{"seed":2**31},
            {"settings":{"fake":{}}},
            {"scenes":{"fake":{}}},
        )
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises((ChunkWorldError,ValueError)):
                    run_chunked_npc_world([],**bad)
        with self.assertRaises(ChunkWorldError):
            run_chunked_npc_world(["wait"]*2,options={"max_turns":1})

    def test_original_scene_source_and_seed_cross_checks(self):
        names=("quest_director","dialogue","npc_society")
        sources={n:make_advanced_scene(n,seed=7) for n in names}
        receipt=run_chunked_npc_world(["wait"],scenes=sources,seed=7)
        self.assertTrue(verify_chunked_npc_world(receipt))
        swapped=deepcopy(sources)
        swapped["dialogue"]=make_advanced_scene("dialogue",seed=8)
        with self.assertRaises((ChunkWorldError,ValueError)):
            run_chunked_npc_world([],scenes=swapped,seed=7)
        changed=deepcopy(sources)
        changed["quest_director"]["layout"]["player_spawn"]=5
        with self.assertRaises((ChunkWorldError,ValueError)):
            run_chunked_npc_world([],scenes=changed,seed=7)

    def test_complete_trace_source_and_offscreen_custody_rejects_tampering(self):
        report=run_chunked_npc_world(["wait"]*4,
                                      options={"chunks_per_side":5,
                                               "active_limit":4})
        edits=(
            lambda x:x["state"]["actors"][0].__setitem__("position",999),
            lambda x:x["state"]["actors"][7].__setitem__("deferred_ticks",0),
            lambda x:x["state"]["scheduler"].__setitem__("forged_offscreen_events",1),
            lambda x:x["state"]["events"].append({"fake":"source"}),
            lambda x:x["trace"][0].__setitem__("after","0"*64),
            lambda x:x["trace"][1]["physical_moves"].append({"from":0,"to":999}),
            lambda x:x["state"].__setitem__("completed",99),
            lambda x:x["source_identities"]["dialogue"].__setitem__("settings_digest","0"*64),
            lambda x:x["options"].__setitem__("active_limit",16),
            lambda x:x.__setitem__("ai_model_weights_promoted",True),
            lambda x:x.__setitem__("digest","0"*64),
        )
        for mutation in edits:
            changed=deepcopy(report)
            mutation(changed)
            with self.subTest(mutation=mutation):
                with self.assertRaises(ChunkWorldError):
                    verify_chunked_npc_world(changed)

    def test_source_replay_is_deterministic_for_seeds_and_camera_budgets(self):
        for seed in (0,1,5,12):
            for width in (3,5):
                with self.subTest(seed=seed,chunks=width):
                    options={"chunks_per_side":width,"citizens":24,"active_limit":8}
                    record=run_chunked_npc_world(
                        ["wait","move:west","move:east","wait"],
                        options=options,seed=seed)
                    self.assertTrue(verify_chunked_npc_world(record))
                    self.assertEqual(record["digest"],run_chunked_npc_world(
                        ["wait","move:west","move:east","wait"],
                        options=options,seed=seed)["digest"])


class ChunkedNPCInterfaces(unittest.TestCase):
    def test_offline_cli_source_and_verification_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            actions=base/"actions.json";source=base/"result.json"
            options=base/"options.json"
            actions.write_text(json.dumps(["wait","move:west"]),encoding="utf-8")
            options.write_text(json.dumps({"chunks_per_side":5,
                                           "citizens":32,"active_limit":6}),
                               encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["chunked-npc-world","--actions",str(actions),
                                      "--options",str(options)]),0)
            record=json.loads(output.getvalue())
            self.assertEqual(record["physical_actor_count"],32)
            source.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-chunked-npc-world","--record",str(source)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            record["state"]["actors"][0]["position"]=0
            source.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-chunked-npc-world",
                                      "--record",str(source)]),2)

    def test_authenticated_studio_returns_readonly_replay_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_streaming_npc","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,authorized=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=8)
                headers={"Content-Type":"application/json"}
                if authorized:
                    headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),headers)
                response=conn.getresponse()
                status,content=response.status,json.loads(response.read())
                conn.close()
                return status,content
            try:
                payload={"actions":["wait","move:west"],"seed":0,
                         "options":{"chunks_per_side":5,"citizens":32,"active_limit":6}}
                self.assertEqual(post("/api/chunked-npc-world",payload,False)[0],403)
                code,response=post("/api/chunked-npc-world",payload)
                self.assertEqual(code,200)
                self.assertTrue(response["independently_verified"])
                self.assertFalse(response["source_files_mutated"])
                self.assertFalse(response["native_chunked_hardware_certified"])
                record=response["record"]
                self.assertEqual(record["state"]["side"],35)
                code,response=post("/api/chunked-npc-world-verify",{"record":record})
                self.assertEqual(code,200)
                self.assertTrue(response["verified"])
                forged=deepcopy(record)
                forged["state"]["scheduler"]["forged_offscreen_events"]=1
                self.assertEqual(post("/api/chunked-npc-world-verify",
                                      {"record":forged})[0],400)
                page=render_workspace_html("x"*32).decode()
                self.assertIn("Chunked NPC World",page)
                self.assertIn("/api/chunked-npc-world",page)
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
