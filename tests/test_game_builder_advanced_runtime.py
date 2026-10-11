"""Advanced gameplay floor: deterministic multi-mechanic execution and verification."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, ENGINES, ACTION_HELP, MAX_TURNS,
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli
from skeleton.ai.game_builder.system_editors import catalog


class AdvancedProgressionTests(unittest.TestCase):
    def test_every_editor_has_enforced_advanced_design_floor(self):
        specs=catalog()
        self.assertEqual(len(specs),43)
        self.assertTrue(all(spec["progression_floor"]=="advanced" for spec in specs))
        self.assertTrue(all(len(spec["advanced_contract"])>=5 for spec in specs))
        self.assertEqual({s["id"] for s in specs
                          if s["runtime_maturity"]=="advanced_reference_runtime"},
                         set(ENGINES))
        self.assertTrue(all(s["runtime_maturity"] in
            {"authoring_only","advanced_reference_runtime"} for s in specs))


class AdvancedPlatformerTests(unittest.TestCase):
    def test_jump_swept_collision_checkpoints_and_evidence(self):
        actions=["jump_right","right","right","right","right","wait","dash_right"]
        state=run_advanced_session("platformer",{"double_jump":True},actions,seed=21)
        self.assertEqual(state["validated_turn_count"],len(actions))
        self.assertTrue(verify_advanced_session(state,{"double_jump":True}))
        self.assertEqual(state,run_advanced_session(
            "platformer",{"double_jump":True},tuple(actions),seed=21))
        self.assertTrue(any("jump" in row["events"] for row in state["trace"]))
        self.assertGreaterEqual(state["state"]["x"],0)
        self.assertLess(state["state"]["x"],60)
        self.assertEqual(state["quality_floor"],"advanced")
        self.assertFalse(state["publication_certified"])
        self.assertFalse(state["native_hardware_verified"])
        self.assertNotEqual(state["trace"][0]["digest"],state["trace"][-1]["digest"])

    def test_hazard_respawn_is_bounded_and_cannot_be_cheated(self):
        session=run_advanced_session("platformer",{"run_speed":3},
                                      ["right","right","right"],seed=0)
        self.assertGreaterEqual(session["state"]["health"],0)
        self.assertLessEqual(session["state"]["x"],59)
        self.assertEqual(session["state"]["tick"],3)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platformer",actions=["fly"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platformer",actions=["dash_right","dash_right"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platformer",actions=["right"]*129)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("platformer",seed=True)


class AdvancedTacticsTests(unittest.TestCase):
    def test_units_ap_enemy_turn_and_cover_provenance(self):
        actions=["east","guard","end_turn","switch","south","end_turn"]
        session=run_advanced_session("tactics",actions=actions,seed=5)
        self.assertEqual(session["state"]["round"],3)
        self.assertTrue(verify_advanced_session(session))
        self.assertGreaterEqual(len(session["state"]["enemies"]),1)
        self.assertIn(session["state"]["active_unit"],(0,1))
        self.assertTrue(any(event.startswith("enemy_") for row in session["trace"]
                            for event in row["events"]))
        self.assertEqual(session["state"]["action_points"],3)
        self.assertFalse(session["terminal"])

    def test_illegal_actions_fail_closed_without_spending_ap(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tactics",actions=["north"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tactics",actions=["attack:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tactics",actions=["heal","heal","heal"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("tactics",actions=["end_turn"]*3)))


class AdvancedDefenseTests(unittest.TestCase):
    def test_waves_upgrade_income_ai_and_targeting(self):
        actions=["build:0","build:1","upgrade:0","priority:strong",
                 "tick:4","tick:4","tick:4","tick:4"]
        session=run_advanced_session("tower_defense",actions=actions)
        self.assertTrue(verify_advanced_session(session))
        state=session["state"]
        self.assertGreater(state["spawned"],0)
        self.assertGreater(state["tick"],0)
        self.assertGreaterEqual(state["defeated"],0)
        self.assertEqual(len(state["towers"]),2)
        self.assertEqual(state["priority"],"strong")
        self.assertLess(state["credits"],60+state["defeated"]*5)
        self.assertEqual(state["towers"][0]["level"],2)
        self.assertTrue(any("tower_fired" in receipt["events"]
                            for receipt in session["trace"]))

    def test_impossible_purchase_and_invalid_upgrade_rejected(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",actions=["build:0","build:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",actions=["upgrade:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",{"starting_credits":0},
                                  actions=["build:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",actions=["sell:2"])


class AdvancedRacingTests(unittest.TestCase):
    def test_weather_vehicle_conditions_and_actual_finish(self):
        commands=["accelerate","accelerate","accelerate","steer_right","coast"]
        session=run_advanced_session("racing",actions=commands,seed=2)
        self.assertEqual(session["state"]["weather"],"storm")
        self.assertEqual(session["state"]["lane"],1)
        self.assertLess(session["state"]["fuel"],session["state"]["fuel_capacity"])
        self.assertGreater(session["state"]["distance"],0)
        self.assertTrue(verify_advanced_session(session))
        finish=run_advanced_session("racing",{"track_length":20,"laps":1},
                                    actions=["accelerate"]*4,seed=1)
        self.assertTrue(finish["state"]["finished"])
        self.assertTrue(finish["terminal"])
        self.assertGreater(finish["state"]["championship_points"],0)
        self.assertTrue(verify_advanced_session(
            finish,{"track_length":20,"laps":1}))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("racing",{"track_length":20,"laps":1},
                                 actions=["accelerate"]*5,seed=1)

    def test_pit_limits_and_cannot_teleport(self):
        pit=run_advanced_session("racing",actions=["pit"],seed=4)
        self.assertEqual(pit["state"]["pit_crews"],2)
        self.assertEqual(pit["state"]["fuel"],pit["state"]["fuel_capacity"])
        self.assertIn("pit_service",pit["trace"][0]["events"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("racing",actions=["pit"]*4)


class AdvancedSurvivalTests(unittest.TestCase):
    def test_finite_resources_crafting_shelter_and_open_ended_outcome(self):
        commands=["gather_wood","mine_stone","craft_tool",
                  "gather_wood","mine_stone","build_shelter","travel"]
        report=run_advanced_session("survival",actions=commands,seed=0)
        self.assertTrue(verify_advanced_session(report))
        state=report["state"]
        self.assertEqual(state["tools"],1)
        self.assertEqual(state["shelter_level"],1)
        self.assertIn("permanent_camp",state["milestones"])
        self.assertEqual(state["region"],1)
        self.assertFalse(state["finished"])
        self.assertFalse(report["terminal"])
        self.assertLess(state["regions"][0]["wood_stock"],16)
        self.assertLess(state["regions"][0]["stone_stock"],7)
        self.assertTrue(any("finite_resource_harvested" in x["events"]
                            for x in report["trace"]))

    def test_no_free_fuel_resources_or_crafting_and_exhaustion_enforced(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("survival",actions=["craft_tool"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("survival",actions=["light_fire"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("survival",actions=["travel"]*4)
        self.assertTrue(verify_advanced_session(
            run_advanced_session("survival",actions=["forage","drink","rest"])))


class AdvancedProofTests(unittest.TestCase):
    def test_hash_chain_replay_and_corruption_detection(self):
        for engine,actions in (
            ("platformer",["jump_right","right","wait"]),
            ("tactics",["east","end_turn"]),
            ("tower_defense",["build:0","tick:4"]),
            ("racing",["accelerate","steer_right","coast"]),
            ("survival",["forage","drink","rest"]),
        ):
            with self.subTest(engine=engine):
                session=run_advanced_session(engine,actions=actions,seed=3)
                self.assertEqual(session["trace"][0]["previous"],
                                 session["baseline_digest"])
                for prior,following in zip(session["trace"],session["trace"][1:]):
                    self.assertEqual(following["previous"],prior["digest"])
                bad=deepcopy(session)
                bad["state"]["finished"]=True
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(bad)
                bad=deepcopy(session)
                bad["trace"][0]["state_digest"]="f"*64
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(bad)
                bad=deepcopy(session)
                bad["head_digest"]="f"*64
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(bad)
                bad=deepcopy(session)
                bad["quality_floor"]="basic"
                with self.assertRaises(AdvancedRuntimeError):
                    verify_advanced_session(bad)

    def test_no_fake_support_for_40_other_systems(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maze")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("rpg")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("nonexistent")


class AdvancedCliTests(unittest.TestCase):
    def test_cli_can_run_and_independently_verify_real_gameplay(self):
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/"moves.json"
            script.write_text(json.dumps(["build:0","tick:4"]),encoding="utf-8")
            output=io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(editor_cli(["play","--editor","tower_defense",
                                             "--actions",str(script),"--seed","3"]),0)
            session=json.loads(output.getvalue())
            self.assertEqual(session["quality_floor"],"advanced")
            trace=Path(tmp)/"receipt.json"
            trace.write_text(json.dumps(session),encoding="utf-8")
            output=io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(editor_cli(["verify-play","--session",str(trace)]),0)
            self.assertTrue(json.loads(output.getvalue())["verified"])
            session["state"]["credits"]=9999
            trace.write_text(json.dumps(session),encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(editor_cli(["verify-play","--session",str(trace)]),2)


class AdvancedStudioAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work=GameWorkspace.create(Path(self.temp.name)/"studio",authorized=True)
        self.work.create_project("active_game","hybrid",authorized=True)
        self.server=create_workspace_server(self.work,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,data,with_token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=7)
        headers={"Content-Type":"application/json"}
        if with_token:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(data),headers)
        response=conn.getresponse()
        result=response.read()
        status=response.status
        conn.close()
        return status,json.loads(result)

    def test_live_stateless_play_verify_and_reject_tampering(self):
        status,data=self.post("/api/advanced-play",
                              {"editor":"tactics","actions":["east","end_turn"],"seed":7})
        self.assertEqual(status,200)
        self.assertFalse(data["server_mutated_game_files"])
        self.assertEqual(data["session"]["validated_turn_count"],2)
        self.assertIn("end_turn",data["available_actions"])
        self.assertEqual(self.post("/api/advanced-play",
                         {"editor":"racing","actions":["accelerate"]})[0],200)
        self.assertEqual(self.post("/api/advanced-play",
                         {"editor":"survival","actions":["gather_wood"]})[0],200)
        self.assertFalse((self.work.root/"current/active_game/systems").exists())
        session=data["session"]
        self.assertEqual(self.post("/api/advanced-verify",
                                  {"session":session})[0],200)
        session["trace"][0]["digest"]="0"*64
        self.assertEqual(self.post("/api/advanced-verify",
                                  {"session":session})[0],400)
        self.assertEqual(self.post("/api/advanced-play",
                                  {"editor":"tactics","actions":["attack:0"]})[0],400)
        self.assertEqual(self.post("/api/advanced-play",
                                  {"editor":"tactics","actions":[]},
                                  with_token=False)[0],403)

    def test_visual_play_surface_is_offline_and_explicit(self):
        html=render_workspace_html("X"*32).decode()
        self.assertIn('id="advanced-canvas"',html)
        self.assertIn('id="advanced-actions"',html)
        self.assertIn('id="advanced-verify"',html)
        self.assertIn('id="advanced-start"',html)
        self.assertIn("Content-Security-Policy",html)
        self.assertNotIn("https://",html)


if __name__=="__main__":
    unittest.main()
