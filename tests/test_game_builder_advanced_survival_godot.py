"""Real authored open-ended survival: native rules, finite resources and custody."""
from __future__ import annotations
from base64 import b64decode
from contextlib import redirect_stdout,redirect_stderr
from copy import deepcopy
from hashlib import sha256
from io import BytesIO,StringIO
from pathlib import Path
from zipfile import ZipFile
import http.client,json,tempfile,threading,unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_survival_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_SURVIVAL,render_survival_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


def authored(seed=0,settings=None,*,regions=None,region=0,weather="rain"):
    cfg=settings or {}
    if regions is None:
        layout=make_advanced_scene("survival",cfg,seed=seed)["layout"]
        regions=layout["regions"]
    return make_advanced_scene("survival",cfg,seed=seed,layout={
        "regions":regions,"starting_region":region,"weather":weather})


class NativeOpenWorldSurvivalTests(unittest.TestCase):
    def test_original_regions_all_state_fields_and_deterministic_source(self):
        for seed,weather in ((0,"clear"),(1,"rain"),(2,"cold"),(3,"heat")):
            with self.subTest(seed=seed):
                settings={"starting_food":10,"starting_water":10}
                scene=authored(seed,settings,region=seed%4,weather=weather)
                actions=["forage","gather_wood","rest","travel","trade","drink"]
                game=run_advanced_session("survival",settings,actions,seed=seed,scene=scene)
                self.assertFalse(game["terminal"])
                self.assertTrue(verify_advanced_session(game,settings))
                pkg=render_survival_godot_package(game,settings,authorized=True)
                self.assertEqual(pkg.manifest["native_editor"],"survival")
                self.assertEqual(pkg.manifest["native_adapter"],
                                 "godot4_independent_open_world_survival")
                self.assertTrue(pkg.manifest["advanced_floor"])
                self.assertFalse(pkg.manifest["godot_executed"])
                self.assertFalse(pkg.manifest["publish_approved"])
                source=json.loads(pkg.files["godot/game.json"])
                proof=json.loads(pkg.files["godot/proof.json"])
                self.assertEqual(source["schema"],SCHEMA)
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(source["scene"],scene)
                self.assertEqual(proof["actions"],actions)
                self.assertEqual(proof["expected"],{
                    key:game["state"][key] for key in PROOF_FIELDS})
                self.assertEqual(pkg.files,render_survival_godot_package(
                    game,settings,authorized=True).files)

    def test_craft_tools_shelter_outpost_without_forced_win(self):
        cfg={"initial_wood":15,"starting_food":15,"starting_water":15}
        scene=authored(0,cfg)
        actions=["mine_stone","mine_stone","craft_tool","build_shelter",
                 "mine_stone","build_shelter","rest","travel"]
        game=run_advanced_session("survival",cfg,actions,seed=0,scene=scene)
        self.assertIn("permanent_camp",game["state"]["milestones"])
        self.assertIn("self_sufficient_outpost",game["state"]["milestones"])
        self.assertFalse(game["state"]["finished"])
        self.assertFalse(game["terminal"])
        self.assertIn("original_world_milestone",[
            event for t in game["trace"] for event in t["events"]])
        self.assertTrue(render_survival_godot_package(game,cfg,authorized=True)
                        .manifest["advanced_floor"])

    def test_survivor_death_is_terminal_without_infinite_replenishment(self):
        cfg={"max_health":2,"starting_food":0,"starting_water":0,
             "hunger_rate":2,"initial_wood":0}
        game=run_advanced_session("survival",cfg,["rest","rest"])
        self.assertTrue(game["state"]["failed"])
        self.assertEqual(game["state"]["health"],0)
        self.assertFalse(game["state"]["finished"])
        pkg=render_survival_godot_package(game,cfg,authorized=True)
        self.assertTrue(json.loads(pkg.files["godot/proof.json"])["expected"]["failed"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("survival",cfg,["rest","rest","rest"])

    def test_finite_trade_cooking_fire_and_biome_resource_depletion(self):
        cfg={"starting_food":10,"starting_water":10,"initial_wood":4}
        scene=authored(0,cfg)
        commands=["hunt","light_fire","cook","trade","forage","rest"]
        game=run_advanced_session("survival",cfg,commands,scene=scene)
        all_events=[e for t in game["trace"] for e in t["events"]]
        for event in ("meal_cooked","finite_market_trade","fire_lit",
                      "finite_resource_harvested"):
            self.assertIn(event,all_events)
        self.assertEqual(game["state"]["trade_tokens"],1)
        self.assertTrue(verify_advanced_session(game,cfg))
        self.assertTrue(render_survival_godot_package(game,cfg,authorized=True)
                        .manifest["advanced_floor"])

    def test_outdated_settings_forgery_unapproved_output_and_original_game(self):
        game=run_advanced_session("survival",actions=["rest"])
        with self.assertRaises(PermissionError):
            render_survival_godot_package(game,authorized=False)
        forged=deepcopy(game);forged["state"]["water"]=999
        with self.assertRaises(AdvancedRuntimeError):
            render_survival_godot_package(forged,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_survival_godot_package(game,{"hunger_rate":3},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_survival_godot_package(run_advanced_session("racing"),authorized=True)
        pkg=render_survival_godot_package(game,authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/"original-survival"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(pkg,output,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                pkg,output,authorized=True),output)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(pkg,output,authorized=True)

    def test_portable_offline_source_and_actual_gameplay_rules(self):
        game=run_advanced_session("survival",actions=["rest","forage"])
        pkg=render_survival_godot_package(game,authorized=True)
        data=archive_advanced_godot_package(pkg)
        self.assertEqual(data,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(data)) as zipfile:
            self.assertEqual(set(zipfile.namelist()),
                {"original-godot-survival/"+f for f in pkg.files})
            for path,blob in pkg.files.items():
                self.assertEqual(zipfile.read("original-godot-survival/"+path),blob)
        for token in ("func _step(","func _verify(","self_sufficient_outpost",
                      "finite_market_trade","weather_exposure","survivor_lost",
                      "NATIVE_ADVANCED_SURVIVAL_OK"):
            self.assertIn(token,GODOT_SURVIVAL)
        for unsafe in ("OS.execute(","HTTPRequest","HTTPClient","eval(",
                       "EditorPlugin"):
            self.assertNotIn(unsafe,GODOT_SURVIVAL)

    def test_authorized_cli_original_world_export(self):
        session=run_advanced_session("survival",actions=["rest"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);input_path=root/"world.json"
            input_path.write_text(json.dumps(session),encoding="utf-8")
            dest=root/"game"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(input_path),
                                      "--output",str(dest)]),2)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(cli(["godot-export","--session",str(input_path),
                         "--output",str(dest),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(stdout.getvalue())["native_editor"],"survival")
            self.assertTrue((dest/"godot/scripts/main.gd").is_file())


class NativeSurvivalStudioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ws=GameWorkspace.create(Path(temp.name)/"game-studio",authorized=True)
        ws.create_project("original_survivor","survival",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        t=threading.Thread(target=self.server.serve_forever,daemon=True)
        t.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,data,token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if token:headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(data),headers)
        response=conn.getresponse()
        status=response.status;payload=json.loads(response.read());conn.close()
        return status,payload

    def test_verified_native_world_zip_and_replay_denial(self):
        settings={"starting_food":8}
        scene=make_advanced_scene("survival",settings,seed=4)
        game=run_advanced_session("survival",settings,
                         ["forage","rest"],seed=4,scene=scene)
        status,reply=self.post("/api/advanced-godot-package",{
            "session":game,"settings":settings})
        self.assertEqual(status,200)
        self.assertEqual(reply["engine"],"survival")
        self.assertEqual(reply["file_name"],"original-godot-survival.zip")
        self.assertFalse(reply["source_project_mutated"])
        self.assertFalse(reply["gameplay_native_verified_by_this_request"])
        zip_bytes=b64decode(reply["zip_base64"],validate=True)
        self.assertEqual(sha256(zip_bytes).hexdigest(),reply["zip_sha256"])
        with ZipFile(BytesIO(zip_bytes)) as archive:
            self.assertIn("original-godot-survival/godot/scripts/main.gd",
                          archive.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":game},token=False)[0],403)
        bad=deepcopy(game);bad["state"]["health"]=300
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":bad,"settings":settings})[0],400)

    def test_studio_accepts_eight_native_games(self):
        html=render_workspace_html("T"*32).decode()
        self.assertIn('"tower_defense","racing","survival","farming","factory"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)


if __name__=="__main__":
    unittest.main()
