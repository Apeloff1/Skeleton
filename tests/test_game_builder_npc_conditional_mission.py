"""Source-replayed conditional original NPC missions and player-knowledge custody."""
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

from skeleton.ai.game_builder.advanced_chunked_npc_world import run_chunked_npc_world
from skeleton.ai.game_builder.advanced_npc_conditional_mission import (
    SCHEMA,OriginalConditionalMissionError,
    run_original_conditional_mission,verify_original_conditional_mission,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


def world(citizens=16,chunks=3,seed=0):
    return run_chunked_npc_world([],seed=seed,options={
        "chunks_per_side":chunks,"citizens":citizens,
        "active_limit":8,"chunk_radius":1,"lod_policy":"fair",
    })


def goal(kind="site",index=0,action="approach"):
    return {"kind":kind,"index":index,"action":action}


def iff(guard,yes,no):
    return {"when":{"if":guard,"then":yes,"otherwise":no}}


def fact(name, **attributes):
    return {"fact":{"predicate":name,**attributes}}


PROGRAM=[
    {"goal":goal(action="harvest")},
    iff({"all":[
        fact("own_harvest_at_site",site=0),
        {"any":[fact("firsthand_testimony",actor=0),
                {"not":fact("paid_support",actor=0)}]},
    ]},[goal("npc",0,"speak")],[goal()]),
    iff({"all":[fact("firsthand_testimony",actor=0),
                fact("supplies_at_least",amount=1)]},
        [goal("npc",0,"support")],[goal()]),
    iff({"all":[fact("paid_support",actor=0),
                {"not":fact("site_quest_resolved",site=0)}]},
        [*[goal(action="repair") for _ in range(5)],
         goal(action="claim")],
        [goal()]),
    iff({"all":[fact("site_quest_resolved",site=0),
                fact("earned_quests_at_least",amount=1),
                fact("turn_at_most",amount=96)]},
        [goal()],[goal()]),
]


class OriginalConditionalWitnessMissionTests(unittest.TestCase):
    def test_actual_conditional_quest_earned_from_player_provenance(self):
        origin=world()
        report=run_original_conditional_mission(origin,PROGRAM)
        self.assertTrue(verify_original_conditional_mission(report))
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["executed_goal_count"],10)
        self.assertEqual(report["decision_count"],4)
        self.assertEqual(report["starting_world_digest"],origin["digest"])
        self.assertEqual(report["result"]["real_quest_milestones"],1)
        self.assertEqual(report["result"]["real_harvested_events"],1)
        self.assertEqual(report["result"]["real_firsthand_testimonies"],1)
        self.assertEqual(report["result"]["real_paid_support_actions"],1)
        self.assertEqual(report["result"]["physical_npcs"],16)
        self.assertEqual([x["branch_taken"] for x in
                          report["evaluated_conditional_nodes"]],
                         ["then"]*4)
        self.assertTrue(report["discarded_branches_not_simulated"])
        self.assertTrue(report["only_player_acquired_knowledge_controls_branches"])
        self.assertFalse(report["model_weights_promoted"])
        self.assertFalse(report["original_project_mutated"])
        self.assertFalse(report["native_hardware_certified"])
        actual=run_chunked_npc_world(
            report["physical_actions"],origin["settings"],
            scenes=origin["source_scenes"],seed=origin["seed"],
            options=origin["options"])
        self.assertEqual(actual["digest"],report["final_world_digest"])
        self.assertEqual(actual["head_digest"],report["final_source_head"])

    def test_original_player_cannot_know_a_witness_before_hearing_them(self):
        program=[
            iff(fact("firsthand_testimony",actor=0),
                [goal("npc",0,"support")],
                [goal(action="approach")]),
        ]
        report=run_original_conditional_mission(world(),program)
        self.assertTrue(verify_original_conditional_mission(report))
        self.assertEqual(report["evaluated_conditional_nodes"][0]["branch_taken"],
                         "otherwise")
        self.assertFalse(report["evaluated_conditional_nodes"][0][
            "original_player_knowledge"]["satisfied"])
        self.assertEqual(report["result"]["real_firsthand_testimonies"],0)
        self.assertEqual(report["result"]["real_quest_milestones"],0)
        self.assertNotIn("support:0",report["physical_actions"])

    def test_true_source_harvest_then_false_unearned_quest_branch(self):
        program=[
            {"goal":goal(action="harvest")},
            iff(fact("site_quest_resolved",site=0),
                [goal(action="claim")],[goal(action="approach")]),
        ]
        report=run_original_conditional_mission(world(),program)
        self.assertTrue(verify_original_conditional_mission(report))
        self.assertEqual(report["decision_count"],1)
        self.assertEqual(report["evaluated_conditional_nodes"][0]["branch_taken"],
                         "otherwise")
        self.assertEqual(report["result"]["real_quest_milestones"],0)
        self.assertEqual(report["result"]["real_harvested_events"],1)
        self.assertNotIn("claim:0",report["physical_actions"])

    def test_player_resources_and_unknown_spy_facts_never_leak(self):
        origin=world()
        false_guard=fact("supplies_at_least",amount=65535)
        actual=run_original_conditional_mission(
            origin,[iff(false_guard,[goal(action="repair")],[goal()])])
        self.assertTrue(verify_original_conditional_mission(actual))
        decision=actual["evaluated_conditional_nodes"][0]
        self.assertEqual(decision["branch_taken"],"otherwise")
        self.assertEqual(decision["original_player_knowledge"]["evidence"]["required_amount"],
                         65535)
        self.assertFalse(decision["original_player_knowledge"]["satisfied"])
        for prohibited in (
            fact("npc_private_agenda",actor=0),
            fact("model_promotion_probability",amount=50),
            fact("source_event_exists",site=0),
        ):
            with self.subTest(guard=prohibited):
                with self.assertRaises(OriginalConditionalMissionError):
                    run_original_conditional_mission(
                        origin,[iff(prohibited,[goal()],[goal()])])

    def test_evidence_operators_do_not_short_circuit_original_checks(self):
        origin=world()
        branch=iff({"any":[
            fact("supplies_at_least",amount=0),
            {"not":fact("earned_quests_at_least",amount=1)},
            fact("stamina_at_least",amount=0),
        ]},[goal()],[goal("npc",0,"support")])
        proof=run_original_conditional_mission(origin,[branch])
        self.assertTrue(verify_original_conditional_mission(proof))
        evidence=proof["evaluated_conditional_nodes"][0]["original_player_knowledge"]
        self.assertEqual(evidence["operator"],"any")
        self.assertEqual(len(evidence["evidence"]),3)
        self.assertTrue(evidence["satisfied"])
        self.assertEqual(proof["executed_goal_count"],1)
        self.assertNotIn("support:0",proof["physical_actions"])

    def test_128_person_35_tile_map_keeps_real_finite_work(self):
        for chunks in (3,5):
            for count in (64,128):
                with self.subTest(chunks=chunks,citizens=count):
                    origin=world(citizens=count,chunks=chunks)
                    proof=run_original_conditional_mission(origin,[
                        {"goal":goal(action="harvest")},
                        iff(fact("own_harvest_at_site",site=0),
                            [goal(action="approach")],
                            [goal(action="claim")]),
                    ],max_steps_per_goal=16)
                    self.assertTrue(verify_original_conditional_mission(proof))
                    self.assertEqual(proof["result"]["physical_npcs"],count)
                    self.assertEqual(proof["result"]["real_harvested_events"],1)
                    self.assertEqual(proof["result"]["real_quest_milestones"],0)
                    self.assertEqual(proof["evaluated_conditional_nodes"][0][
                                     "branch_taken"],"then")
                    self.assertEqual(
                        proof["result"]["detailed_npc_updates"]+
                        proof["result"]["deferred_npc_turns"],
                        proof["result"]["world_tick"]*count)

    def test_unsupported_guard_trees_invalid_branch_types_and_bounds_denied(self):
        origin=world()
        bad_guards=[
            {}, {"not":{}}, {"all":[]}, {"any":[fact("supplies_at_least",amount=0)]*7},
            {"all":[{"all":[{"all":[{"all":[{"all":[{"all":[
                fact("supplies_at_least",amount=0)]}]}]}]}]}]},
            {"fact":{"predicate":"supplies_at_least","amount":True}},
            {"fact":{"predicate":"paid_support","actor":True}},
            {"fact":{"predicate":"turn_at_most","amount":129}},
            {"fact":{"predicate":"own_harvest_at_site","site":999}},
            {"fact":{"predicate":"earned_quests_at_least","amount":-1}},
            {"fact":{"predicate":"stamina_at_least","amount":0,"spy":True}},
            {"all":[fact("supplies_at_least",amount=0)]*32},
        ]
        for predicate in bad_guards:
            with self.subTest(predicate=predicate):
                with self.assertRaises(OriginalConditionalMissionError):
                    run_original_conditional_mission(
                        origin,[iff(predicate,[goal()],[goal()])])
        for script in (
            [],[None],[{"wrong":goal()}],
            [iff(fact("turn_at_most",amount=1),
                 [goal()]*13,[goal()])],
            [{"when":{"if":fact("turn_at_most",amount=1),
                      "then":[goal()]}}],
            [{"goal":{"kind":"site","index":True,"action":"harvest"}}],
            [{"goal":goal()}]*13,
            [iff(fact("turn_at_most",amount=1),
                 [goal()]*10,[goal()]*10),{"goal":goal()}]*2,
        ):
            with self.subTest(script=script):
                with self.assertRaises(OriginalConditionalMissionError):
                    run_original_conditional_mission(origin,script)
        for limit in (0,73,True,"12"):
            with self.assertRaises(OriginalConditionalMissionError):
                run_original_conditional_mission(origin,PROGRAM,
                                                 max_steps_per_goal=limit)

    def test_source_and_selected_decision_custody_rejects_forgeries(self):
        record=run_original_conditional_mission(world(),PROGRAM)
        mutations=[
            lambda x:x["starting_world"]["state"]["inventory"].__setitem__("supplies",999),
            lambda x:x["evaluated_conditional_nodes"][0].__setitem__("branch_taken","otherwise"),
            lambda x:x["evaluated_conditional_nodes"][1][
                "original_player_knowledge"].__setitem__("satisfied",False),
            lambda x:x["evaluated_conditional_nodes"][0][
                "discarded_unexecuted_goals"].append(goal(action="claim")),
            lambda x:x["actual_goal_executions"][0].__setitem__("real_source_quest_delta",5),
            lambda x:x["actual_goal_executions"][1]["real_actions"].append("support:0"),
            lambda x:x["result"]["inventory"].__setitem__("supplies",999),
            lambda x:x.__setitem__("model_weights_promoted",True),
            lambda x:x.__setitem__("discarded_branches_not_simulated",False),
            lambda x:x.__setitem__("final_world_digest","0"*64),
            lambda x:x.__setitem__("digest","0"*64),
        ]
        for attack in mutations:
            corrupted=deepcopy(record);attack(corrupted)
            with self.subTest(attack=attack):
                with self.assertRaises(OriginalConditionalMissionError):
                    verify_original_conditional_mission(corrupted)


class OriginalConditionalMissionInterfaces(unittest.TestCase):
    def test_offline_cli_run_verify_and_fake_branch_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/"world.json";program=folder/"program.json"
            proof=folder/"proof.json"
            source.write_text(json.dumps(world()),encoding="utf-8")
            program.write_text(json.dumps(PROGRAM),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["run-original-conditional-npc-mission",
                    "--record",str(source),"--program",str(program)]),0)
            record=json.loads(output.getvalue())
            self.assertEqual(record["result"]["real_quest_milestones"],1)
            proof.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-original-conditional-npc-mission",
                    "--record",str(proof)]),0)
            self.assertEqual(json.loads(output.getvalue()),{"verified":True})
            record["evaluated_conditional_nodes"][0]["branch_taken"]="otherwise"
            proof.write_text(json.dumps(record),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-original-conditional-npc-mission",
                    "--record",str(proof)]),2)

    def test_local_studio_requires_auth_and_proves_real_player_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=GameWorkspace.create(Path(temp)/"studio",authorized=True)
            ws.create_project("source_witnessed_conditionals","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def post(path,body,authenticated=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=45)
                h={"Content-Type":"application/json"}
                if authenticated:h["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),h)
                response=conn.getresponse()
                status,answer=response.status,json.loads(response.read())
                conn.close()
                return status,answer
            try:
                input={"record":world(),"program":PROGRAM,"max_steps_per_goal":24}
                self.assertEqual(post("/api/run-original-conditional-npc-mission",
                                      input,False)[0],403)
                status,out=post("/api/run-original-conditional-npc-mission",input)
                self.assertEqual(status,200)
                self.assertTrue(out["verified"])
                self.assertFalse(out["source_files_mutated"])
                self.assertEqual(out["record"]["result"]["real_quest_milestones"],1)
                status,verified=post("/api/verify-original-conditional-npc-mission",
                                     {"record":out["record"]})
                self.assertEqual(status,200)
                self.assertTrue(verified["verified"])
                fake=deepcopy(out["record"])
                fake["evaluated_conditional_nodes"][2][
                    "original_player_knowledge"]["satisfied"]=False
                self.assertEqual(post("/api/verify-original-conditional-npc-mission",
                                      {"record":fake})[0],400)
                self.assertIn("Witness-Conditional Missions",
                              render_workspace_html("x"*32).decode())
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
