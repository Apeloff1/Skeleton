"""Authoritative unified NPC world regression, legal spatial events and custody."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_unified_npc_world import (
    SCHEMA, SIDE, ACTIONS, ORDER, ACTOR_PREFIX, UnifiedWorldError,
    run_unified_npc_world, verify_unified_npc_world,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene

EARNED = ["move:south","move:east","discover:0",
          "speak:0","support:0"]+["followup:0"]*5+["resolve:0"]


class UnifiedOriginalWorldTests(unittest.TestCase):
    def test_single_real_physical_world_earns_a_paid_social_quest(self):
        report=run_unified_npc_world(EARNED)
        self.assertTrue(verify_unified_npc_world(report))
        self.assertEqual(report["schema"],SCHEMA)
        state=report["state"]
        self.assertEqual(state["player"],8)
        self.assertEqual(state["resolved_count"],1)
        self.assertEqual(len(state["quests"]),1)
        quest=state["quests"][0]
        self.assertEqual(quest["status"],"resolved")
        self.assertEqual(quest["followups"],5)
        self.assertEqual(quest["pledges"],[0])
        self.assertEqual(quest["testimonies"],[0])
        self.assertEqual(quest["direct_witnesses"][0],0)
        self.assertEqual(quest["choice"],"support")
        self.assertEqual(len(state["events_ledger"]),1)
        self.assertEqual(state["events_ledger"][0]["kind"],"discover")
        self.assertIn(0,state["events_ledger"][0]["direct_witnesses"])
        self.assertEqual(state["dialogues"][0]["source"],
                         "direct_original_world_eyewitness")
        self.assertEqual(state["dialogues"][0]["event_id"],0)
        self.assertTrue(state["actors"][0]["supported"])
        self.assertEqual(state["actors"][0]["id"],ACTOR_PREFIX+"0")
        self.assertEqual(state["actors"][0]["heard_firsthand"],[0])
        self.assertEqual(state["resources"]["influence"],
                         report["settings"]["dialogue"]["starting_influence"]-
                         report["settings"]["dialogue"]["support_cost"])
        self.assertEqual(state["sites"][0]["aid_received"],
                         report["settings"]["quest_director"]["help_supplies"]*6)
        self.assertEqual(report["canonical_physical_actor_count"],
                         len(state["actors"]))
        self.assertFalse(report["legacy_engines_simultaneously_executed"])
        self.assertFalse(report["native_unified_engine_executed"])
        self.assertFalse(report["source_files_mutated"])
        self.assertFalse(report["model_weights_promoted"])
        self.assertEqual(len(report["event_frames"]),len(EARNED))
        self.assertTrue(all(x["ordered_phases"]==list(ORDER)
                            for x in report["event_frames"]))
        retired=run_unified_npc_world(EARNED+["retire"])
        self.assertTrue(retired["state"]["finished"])
        self.assertTrue(retired["state"]["retired"])
        self.assertTrue(verify_unified_npc_world(retired))

    def test_actor_id_and_physical_position_cannot_duplicate_or_teleport(self):
        commands=["wait"]*16
        record=run_unified_npc_world(commands)
        self.assertTrue(verify_unified_npc_world(record))
        actors=record["state"]["actors"]
        self.assertEqual(len(set(x["id"] for x in actors)),len(actors))
        self.assertEqual(len(set(x["position"] for x in actors)),len(actors))
        self.assertTrue(all(x["movement_steps"]<=len(commands) for x in actors))
        self.assertTrue(all(0<=x["position"]<SIDE*SIDE for x in actors))
        for frame in record["event_frames"]:
            for step in frame["npc_moves"]:
                a,b=step["from"],step["to"]
                self.assertEqual(abs(a%SIDE-b%SIDE)+abs(a//SIDE-b//SIDE),1)
                self.assertEqual(step["path"],"one_real_tile")
                self.assertEqual(step["tick"],frame["tick"])
        self.assertTrue(any(f["npc_moves"] for f in record["event_frames"]))
        self.assertTrue(all("previous" in row and "after" in row
                            for row in record["event_frames"]))

    def test_unwitnessed_material_events_do_not_issue_phantom_quests(self):
        # A single authored nearby witness can be blocked from attesting by
        # lowering perception to one tile; the material event still exists.
        settings={"quest_director":{"npc_perception":1,"witness_radius":1,
                                    "npc_count":1}}
        scene=run_unified_npc_world(["move:south","move:east","discover:0"],
                                    settings)
        self.assertTrue(verify_unified_npc_world(scene))
        log=scene["state"]["events_ledger"][0]
        self.assertEqual(log["original_source"],
                         "physical_same_world_player_action")
        self.assertFalse(scene["state"]["failed"])
        self.assertTrue(all(w in (0,) for w in log["direct_witnesses"]))

    def test_incomplete_games_stay_playable_and_false_quest_completion_denied(self):
        for actions in ([],["wait"],["move:south"],
                        ["move:south","move:east","discover:0"],
                        ["move:south","move:east","discover:0","speak:0"]):
            with self.subTest(actions=actions):
                record=run_unified_npc_world(actions)
                self.assertTrue(verify_unified_npc_world(record))
                self.assertFalse(record["state"]["finished"])
                self.assertEqual(record["state"]["resolved_count"],0)
        with self.assertRaises(UnifiedWorldError):
            run_unified_npc_world(["resolve:0"])
        with self.assertRaises(UnifiedWorldError):
            run_unified_npc_world(["retire"])
        with self.assertRaises(UnifiedWorldError):
            run_unified_npc_world(EARNED[:5]+["resolve:0"])

    def test_real_locality_and_an_observed_speech_are_mandatory(self):
        for actions in (
            ["speak:0"],["support:0"],["resolve:0"],
            ["move:east","move:east"],["move:north"],
            ["discover:0"],["move:south","support:0"],
            ["move:south","move:east","discover:0","support:0"],
            ["move:south","move:east","discover:0",
             "speak:0","followup:0"],
            ["move:south","move:east","discover:0",
             "speak:0","support:0","council:0"],
        ):
            with self.subTest(actions=actions):
                with self.assertRaises(UnifiedWorldError):
                    run_unified_npc_world(actions)

    def test_conservation_consumes_material_and_protects_event_history(self):
        source=run_unified_npc_world([])
        built=run_unified_npc_world(EARNED)
        q=built["settings"]["quest_director"]
        first=source["state"]
        last=built["state"]
        self.assertEqual(
            last["resources"]["supplies"],
            first["resources"]["supplies"] + q["gather_units"] -
            q["help_supplies"]*6,
        )
        self.assertEqual(first["sites"][0]["stock"]-last["sites"][0]["stock"],
                         q["gather_units"])
        self.assertEqual(last["resources"]["gold"],
                         first["resources"]["gold"]+q["reward_gold"])
        self.assertTrue(last["actors"][0]["witness_memories"])
        self.assertEqual(last["events_ledger"][0]["id"],0)

    def test_memory_expiry_does_not_authorize_rumor_as_firsthand(self):
        cfg={"dialogue":{"memory_turns":1}}
        first=run_unified_npc_world(["move:south","move:east","discover:0",
                                     "speak:0","wait"],cfg)
        self.assertTrue(verify_unified_npc_world(first))
        actor=first["state"]["actors"][0]
        self.assertEqual(actor["dialogue_memories"],[])
        self.assertEqual(actor["heard_firsthand"],[0])
        self.assertEqual(first["state"]["dialogues"][0]["event_id"],0)

    def test_multiple_original_seeds_and_authored_source_identity(self):
        for seed in (0,1,2,7):
            with self.subTest(seed=seed):
                one=run_unified_npc_world(EARNED,seed=seed)
                self.assertTrue(verify_unified_npc_world(one))
                self.assertEqual(one["state"]["resolved_count"],1)
                self.assertEqual(
                    one["source_identities"]["quest_director"]["source_scene_digest"],
                    one["sources"]["quest_director"]["digest"])
        authored={name:make_advanced_scene(name,seed=0) for name in
                  ("dialogue","npc_society","quest_director")}
        reread=run_unified_npc_world(EARNED,scenes=authored)
        self.assertTrue(verify_unified_npc_world(reread))
        forged=deepcopy(authored)
        forged["quest_director"]["layout"]["player_spawn"]=8
        with self.assertRaises((UnifiedWorldError,ValueError)):
            run_unified_npc_world([],scenes=forged)
        wrong=deepcopy(authored)
        wrong["dialogue"]=make_advanced_scene("dialogue",seed=1)
        with self.assertRaises(UnifiedWorldError):
            run_unified_npc_world([],scenes=wrong)

    def test_source_schema_and_input_budgets_are_strict(self):
        for bad in (
            (["teleport:30"],{}),
            (["move:north"],{}),
            (["wait"]*97,{}),
            ([12],{}),
            (["wait"],{"seed":True}),
            (["wait"],{"seed":2**31}),
            (["wait"],{"settings":{"fake":{}}}),
            (["wait"],{"settings":{"quest_director":False}}),
        ):
            actions,kwargs=bad
            with self.subTest(bad=bad):
                with self.assertRaises((UnifiedWorldError,ValueError)):
                    run_unified_npc_world(actions,**kwargs)

    def test_mutation_of_entire_world_and_events_cannot_forge_saved_proof(self):
        original=run_unified_npc_world(EARNED)
        for attack in (
            lambda r:r["state"]["actors"][0].__setitem__("position",48),
            lambda r:r["state"]["actors"][0].__setitem__("trust",999),
            lambda r:r["state"]["actors"][0]["witness_memories"][0].__setitem__("source","rumor"),
            lambda r:r["state"]["resources"].__setitem__("gold",2000),
            lambda r:r["state"]["quests"][0].__setitem__("followups",50),
            lambda r:r["state"]["events_ledger"][0].__setitem__("direct_witnesses",[]),
            lambda r:r["state"]["dialogues"][0].__setitem__("event_id",77),
            lambda r:r["event_frames"][2].__setitem__("after","b"*64),
            lambda r:r["source_identities"]["dialogue"].__setitem__("settings_digest","f"*64),
            lambda r:r.__setitem__("native_unified_engine_executed",True),
            lambda r:r.__setitem__("digest","0"*64),
        ):
            altered=deepcopy(original)
            attack(altered)
            with self.subTest(attack=attack):
                with self.assertRaises(UnifiedWorldError):
                    verify_unified_npc_world(altered)


class UnifiedWorldInterfaces(unittest.TestCase):
    def test_cli_round_trip_is_canonical_json_and_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);moves=root/"steps.json";receipt=root/"world.json"
            moves.write_text(json.dumps(EARNED),encoding="utf-8")
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(cli(["unified-npc-world","--actions",str(moves)]),0)
            output=json.loads(captured.getvalue())
            self.assertEqual(output["state"]["resolved_count"],1)
            receipt.write_text(json.dumps(output),encoding="utf-8")
            with redirect_stdout(StringIO()) as result:
                self.assertEqual(cli(["verify-unified-npc-world","--record",str(receipt)]),0)
            self.assertEqual(json.loads(result.getvalue()),{"verified":True})
            output["state"]["resources"]["gold"]+=1
            receipt.write_text(json.dumps(output),encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-unified-npc-world","--record",str(receipt)]),2)

    def test_authorized_studio_replays_real_world_without_source_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=GameWorkspace.create(Path(tmp)/"studio",authorized=True)
            ws.create_project("shared_npc_authority","hybrid",authorized=True)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            def post(path,body,authenticated=True):
                conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=8)
                headers={"Content-Type":"application/json"}
                if authenticated:
                    headers["X-Game-Studio-Token"]=server.secret
                conn.request("POST",path,json.dumps(body),headers)
                res=conn.getresponse()
                code,data=res.status,json.loads(res.read())
                conn.close()
                return code,data
            try:
                self.assertEqual(post("/api/unified-npc-world",{"actions":EARNED},False)[0],403)
                status,payload=post("/api/unified-npc-world",{"actions":EARNED})
                self.assertEqual(status,200)
                self.assertTrue(payload["independently_verified"])
                self.assertFalse(payload["source_files_mutated"])
                self.assertFalse(payload["native_unified_engine_executed"])
                report=payload["record"]
                self.assertEqual(report["state"]["resolved_count"],1)
                code,verified=post("/api/unified-npc-world-verify",{"record":report})
                self.assertEqual(code,200)
                self.assertTrue(verified["verified"])
                tampered=deepcopy(report)
                tampered["state"]["actors"][0]["position"]=42
                self.assertEqual(post("/api/unified-npc-world-verify",
                                      {"record":tampered})[0],400)
                page=render_workspace_html("x"*32).decode()
                self.assertIn("Unified NPC World",page)
                self.assertIn("/api/unified-npc-world",page)
            finally:
                server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
