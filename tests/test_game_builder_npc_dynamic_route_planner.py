"""Real re-planned player traversal of original 128-NPC streamed worlds."""
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
from skeleton.ai.game_builder.advanced_npc_dynamic_route_planner import (
    SCHEMA,OriginalRouteError,plan_original_dynamic_route,
    verify_original_dynamic_route,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def game(citizens=16,chunks=3,seed=0,actions=()):
    return run_chunked_npc_world(actions,seed=seed,options={
        "chunks_per_side":chunks,"citizens":citizens,"active_limit":8,
        "chunk_radius":1,"lod_policy":"fair",
    })


class OriginalDynamicRouteTests(unittest.TestCase):
    def test_source_site_traversal_real_harvest_must_pay_and_be_replayed(self):
        source=game()
        plan=plan_original_dynamic_route(
            source,{"kind":"site","index":0,"action":"harvest"},max_steps=8)
        self.assertTrue(verify_original_dynamic_route(plan))
        self.assertEqual(plan["schema"],SCHEMA)
        self.assertTrue(plan["arrived_at_source_objective"])
        self.assertTrue(plan["performed_optional_real_interaction"])
        self.assertIn("harvest:0",plan["generated_actions"])
        self.assertEqual(plan["actual_action_receipts"][-1]["command"],
                         "harvest:0")
        self.assertGreater(plan["result_summary"]["source_events"],0)
        self.assertGreater(plan["result_summary"]["inventory"]["supplies"],
                           source["state"]["inventory"]["supplies"])
        self.assertLess(plan["result_summary"]["inventory"]["stamina"],
                        source["state"]["inventory"]["stamina"])
        self.assertFalse(plan["hardware_performance_certified"])
        self.assertFalse(plan["model_weights_promoted"])
        self.assertFalse(plan["replanning_is_optimal_global_time_path"])
        actual=run_chunked_npc_world(
            plan["generated_actions"],source["settings"],
            scenes=source["source_scenes"],seed=source["seed"],
            options=source["options"])
        self.assertEqual(actual["digest"],plan["result_world_digest"])
        self.assertEqual(actual["head_digest"],plan["result_head"])
        self.assertTrue(verify_chunked_npc_world(actual))

    def test_preexisting_game_history_remains_exactly_owned_by_source(self):
        source=game(actions=["wait","wait"])
        goal={"kind":"site","index":0,"action":"approach"}
        route=plan_original_dynamic_route(source,goal,max_steps=12)
        self.assertTrue(verify_original_dynamic_route(route))
        self.assertEqual(route["source_head"],source["head_digest"])
        self.assertEqual(route["original_source_digest"],source["digest"])
        self.assertTrue(route["arrived_at_source_objective"])
        self.assertEqual(route["starting_player_cell"],source["state"]["player"])
        if route["generated_actions"]:
            self.assertEqual(
                route["actual_action_receipts"][0]["turn"],
                len(source["commands"])+1)
        actual=run_chunked_npc_world(
            source["commands"]+route["generated_actions"],
            source["settings"],scenes=source["source_scenes"],
            seed=source["seed"],options=source["options"])
        self.assertEqual(actual["digest"],route["result_world_digest"])
        self.assertEqual(actual["head_digest"],route["result_head"])

    def test_npc_approach_is_physically_valid_and_never_teleports(self):
        source=game()
        route=plan_original_dynamic_route(
            source,{"kind":"npc","index":0,"action":"approach"},
            max_steps=16)
        self.assertTrue(verify_original_dynamic_route(route))
        self.assertTrue(route["arrived_at_source_objective"])
        side=source["state"]["side"]
        for step in route["actual_action_receipts"]:
            a,b=step["from"],step["to"]
            distance=abs(a%side-b%side)+abs(a//side-b//side)
            self.assertLessEqual(distance,1)
            if step["command"].startswith("move:"):
                self.assertEqual(distance,1)
            else:
                self.assertEqual(distance,0)

    def test_routing_to_a_real_cell_stays_adjacent_step_by_step(self):
        source=game()
        target=source["state"]["player"]+1
        if target in source["state"]["obstacles"]:
            target=source["state"]["player"]+source["state"]["side"]
        route=plan_original_dynamic_route(
            source,{"kind":"cell","index":target,"action":"approach"},
            max_steps=8)
        self.assertTrue(verify_original_dynamic_route(route))
        self.assertEqual(route["result_summary"]["player"],target)
        self.assertTrue(route["arrived_at_source_objective"])
        self.assertFalse(route["performed_optional_real_interaction"])
        self.assertTrue(all(x["command"].startswith("move:") or
                            x["command"] in ("rest","wait")
                            for x in route["actual_action_receipts"]))

    def test_existing_path_already_at_goal_needs_no_fabricated_action(self):
        source=game()
        target=source["state"]["player"]
        route=plan_original_dynamic_route(
            source,{"kind":"cell","index":target,"action":"approach"},
            max_steps=3)
        self.assertTrue(verify_original_dynamic_route(route))
        self.assertEqual(route["generated_actions"],[])
        self.assertEqual(route["actual_action_receipts"],[])
        self.assertEqual(route["result_world_digest"],source["digest"])
        self.assertEqual(route["result_head"],source["head_digest"])

    def test_true_crowded_worlds_still_remain_source_replayable(self):
        for count in (16,64,128):
            for chunks in (3,5):
                source=game(citizens=count,chunks=chunks)
                goal={"kind":"site","index":0,"action":"harvest"}
                route=plan_original_dynamic_route(source,goal,max_steps=12)
                with self.subTest(citizens=count,chunks=chunks):
                    self.assertTrue(verify_original_dynamic_route(route))
                    self.assertTrue(route["arrived_at_source_objective"])
                    self.assertEqual(route["result_summary"]["physically_embodied_npcs"],
                                     count)
                    self.assertEqual(route["result_summary"]["source_events"],1)
                    self.assertTrue(all(x["actual_detailed_npcs"]<=8
                                        for x in route["actual_action_receipts"]))

    def test_true_physical_source_rejects_impossible_actions_and_malformed_goal(self):
        source=game()
        for objective in (
            {"kind":"imaginary","index":0,"action":"approach"},
            {"kind":"site","index":8,"action":"approach"},
            {"kind":"npc","index":128,"action":"speak"},
            {"kind":"cell","index":-1,"action":"approach"},
            {"kind":"cell","index":441,"action":"approach"},
            {"kind":"site","index":0,"action":"teleport"},
            {"kind":"cell","index":0,"action":"harvest"},
            {"kind":"npc","index":0,"action":"claim"},
            {"kind":"site","index":0,"action":"approach","bonus":True},
            {"kind":"site","index":True,"action":"harvest"},
        ):
            with self.subTest(objective=objective):
                with self.assertRaises(OriginalRouteError):
                    plan_original_dynamic_route(source,objective)
        for steps in (0,73,True,-1,"8"):
            with self.subTest(steps=steps):
                with self.assertRaises(OriginalRouteError):
                    plan_original_dynamic_route(
                        source,{"kind":"site","index":0,"action":"harvest"},
                        max_steps=steps)

    def test_false_quest_claim_and_restoration_without_real_source_work_are_rejected(self):
        source=game()
        with self.assertRaises(OriginalRouteError):
            plan_original_dynamic_route(
                source,{"kind":"site","index":0,"action":"claim"},
                max_steps=10)
        with self.assertRaises(OriginalRouteError):
            plan_original_dynamic_route(
                source,{"kind":"site","index":0,"action":"repair"},
                max_steps=10)

    def test_tampered_game_source_and_path_receipts_fail_closed(self):
        original=plan_original_dynamic_route(
            game(),{"kind":"site","index":0,"action":"harvest"},max_steps=8)
        for mutate in (
            lambda r:r["source_game"]["state"]["actors"][0].__setitem__("position",400),
            lambda r:r["source_game"]["state"]["inventory"].__setitem__("stamina",999),
            lambda r:r["objective"].__setitem__("kind","npc"),
            lambda r:r.__setitem__("starting_player_cell",200),
            lambda r:r["actual_action_receipts"][0].__setitem__("to",999),
            lambda r:r["actual_action_receipts"][-1].__setitem__("source_frame","0"*64),
            lambda r:r.__setitem__("result_world_digest","0"*64),
            lambda r:r["result_summary"].__setitem__("earned_quests",99),
            lambda r:r.__setitem__("hardware_performance_certified",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            forged=deepcopy(original);mutate(forged)
            with self.subTest(mutation=mutate):
                with self.assertRaises(OriginalRouteError):
                    verify_original_dynamic_route(forged)

    def test_world_turn_budget_refuses_unachievable_path_without_fake_progress(self):
        source=game(actions=["wait"]*25)
        with self.assertRaises(OriginalRouteError):
            plan_original_dynamic_route(
                source,{"kind":"site","index":0,"action":"harvest"},
                max_steps=72)


class OriginalDynamicRouteInterfaces(unittest.TestCase):
    def test_cli_plan_and_independent_verification_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            game_file=root/"world.json";objective=root/"goal.json";receipt=root/"route.json"
            game_file.write_text(json.dumps(game()),encoding="utf-8")
            objective.write_text(json.dumps({
                "kind":"site","index":0,"action":"harvest",
            }),encoding="utf-8")
            with redirect_stdout(StringIO()) as response:
                self.assertEqual(cli(["plan-original-npc-route","--record",str(game_file),
                    "--objective",str(objective),"--max-steps","8"]),0)
            result=json.loads(response.getvalue())
            self.assertTrue(result["arrived_at_source_objective"])
            receipt.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stdout(StringIO()) as response:
                self.assertEqual(cli(["verify-original-npc-route","--record",str(receipt)]),0)
            self.assertEqual(json.loads(response.getvalue()),{"verified":True})
            result["result_summary"]["inventory"]["supplies"]=999
            receipt.write_text(json.dumps(result),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-original-npc-route",
                                      "--record",str(receipt)]),2)

    def test_studio_requires_token_and_replay_proof_before_route_result(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("original_dynamic_pathfinding","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(endpoint,payload,authorized=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=20)
                headers={"Content-Type":"application/json"}
                if authorized:headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",endpoint,json.dumps(payload),headers)
                r=conn.getresponse();code,data=r.status,json.loads(r.read())
                conn.close();return code,data
            try:
                payload={"record":game(),
                         "objective":{"kind":"site","index":0,"action":"harvest"},
                         "max_steps":8}
                self.assertEqual(post("/api/plan-original-npc-route",payload,False)[0],403)
                code,result=post("/api/plan-original-npc-route",payload)
                self.assertEqual(code,200)
                self.assertTrue(result["verified"])
                self.assertFalse(result["source_files_mutated"])
                self.assertTrue(result["record"]["arrived_at_source_objective"])
                code,verified=post("/api/verify-original-npc-route",{
                    "record":result["record"]})
                self.assertEqual(code,200)
                self.assertTrue(verified["verified"])
                forged=deepcopy(result["record"])
                forged["actual_action_receipts"][-1]["source_frame"]="0"*64
                self.assertEqual(post("/api/verify-original-npc-route",{
                    "record":forged})[0],400)
                self.assertIn("Dynamic NPC Route Planner",
                              render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
