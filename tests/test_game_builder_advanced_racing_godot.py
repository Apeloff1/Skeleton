"""Original native circuit racing simulation, export custody and studio tests."""
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
from skeleton.ai.game_builder.advanced_racing_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_RACING,render_racing_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


class NativeCircuitRacingProofTests(unittest.TestCase):
    def test_seeded_weather_corners_full_state_native_source(self):
        settings={"track_length":60,"laps":2,"max_speed":15}
        for seed,weather in ((0,"dry"),(1,"wet"),(2,"storm")):
            with self.subTest(weather=weather):
                scene=make_advanced_scene("racing",settings,seed=seed)
                actions=["accelerate","steer_right","boost","coast","brake"]
                game=run_advanced_session("racing",settings,actions,seed=seed,scene=scene)
                self.assertTrue(verify_advanced_session(game,settings))
                pkg=render_racing_godot_package(game,settings,authorized=True)
                self.assertEqual(pkg.manifest["native_editor"],"racing")
                self.assertEqual(pkg.manifest["native_adapter"],
                                 "godot4_independent_circuit_racing")
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
                    field:game["state"][field] for field in PROOF_FIELDS})
                self.assertEqual(pkg.files,render_racing_godot_package(
                    game,settings,authorized=True).files)

    def test_victory_laps_and_championship_scoring(self):
        cfg={"track_length":20,"laps":1,"max_speed":15,"acceleration":10}
        scene=make_advanced_scene("racing",cfg,seed=0,layout={
            "corners":[4,10],"track_obstacle":7,"weather":"dry",
            "starting_lane":1})
        game=run_advanced_session("racing",cfg,["accelerate","accelerate"],
                                  seed=0,scene=scene)
        self.assertTrue(game["terminal"])
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(game["state"]["lap"],1)
        self.assertGreater(game["state"]["championship_points"],0)
        self.assertEqual(game["state"]["distance"],20)
        native=render_racing_godot_package(game,cfg,authorized=True)
        self.assertTrue(json.loads(native.files["godot/proof.json"])["expected"]["finished"])

    def test_real_pit_repairs_weather_damage_and_nitro_consumption(self):
        cfg={"track_length":40,"laps":2,"max_speed":24}
        scene=make_advanced_scene("racing",cfg,seed=5,layout={
            "corners":[3,6,13,25],"track_obstacle":7,
            "weather":"storm","starting_lane":0})
        game=run_advanced_session("racing",cfg,
              ["accelerate","brake","pit","boost","steer_right","accelerate"],
              seed=5,scene=scene)
        self.assertEqual(game["state"]["pit_stops"],1)
        self.assertEqual(game["state"]["pit_crews"],2)
        self.assertEqual(game["state"]["boost_charges"],2)
        self.assertIn("boost_consumed",[
            event for item in game["trace"] for event in item["events"]])
        self.assertIn("pit_service",[
            event for item in game["trace"] for event in item["events"]])
        self.assertEqual(render_racing_godot_package(
            game,cfg,authorized=True).manifest["advanced_floor"],True)

    def test_fail_closed_for_forged_session_outdated_settings_and_unsafe_write(self):
        session=run_advanced_session("racing",actions=["accelerate"])
        with self.assertRaises(PermissionError):
            render_racing_godot_package(session,authorized=False)
        tampered=deepcopy(session);tampered["state"]["fuel"]=9999
        with self.assertRaises(AdvancedRuntimeError):
            render_racing_godot_package(tampered,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_racing_godot_package(session,{"laps":2},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_racing_godot_package(run_advanced_session("survival"),authorized=True)
        pkg=render_racing_godot_package(session,authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"original-race"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(pkg,dest,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                pkg,dest,authorized=True),dest)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(pkg,dest,authorized=True)

    def test_portable_content_addressed_zip_and_real_native_logic(self):
        receipt=run_advanced_session("racing",actions=["accelerate","coast"])
        pkg=render_racing_godot_package(receipt,authorized=True)
        data=archive_advanced_godot_package(pkg)
        self.assertEqual(data,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(data)) as bundle:
            self.assertEqual(set(bundle.namelist()),
                {"original-godot-racing/"+p for p in pkg.files})
            for name,body in pkg.files.items():
                self.assertEqual(bundle.read("original-godot-racing/"+name),body)
        for phrase in ("func _step(","func _verify(","centerline_obstacle_hit",
                       "corner_understeer_damage","pit_service",
                       "mechanical_limp_mode","race_completed",
                       "NATIVE_ADVANCED_RACING_OK"):
            self.assertIn(phrase,GODOT_RACING)
        for unsafe in ("OS.execute(","HTTPRequest","HTTPClient","eval(",
                       "EditorPlugin"):
            self.assertNotIn(unsafe,GODOT_RACING)

    def test_operator_only_cli_writes_original_racing_game(self):
        session=run_advanced_session("racing",actions=["accelerate"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            inp=root/"race.json";inp.write_text(json.dumps(session))
            out=root/"original-game"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(inp),
                                      "--output",str(out)]),2)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["godot-export","--session",str(inp),
                    "--output",str(out),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(output.getvalue())["native_editor"],"racing")
            self.assertTrue((out/"godot/scripts/main.gd").is_file())


class NativeRacingStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ws=GameWorkspace.create(Path(self.temp.name)/"studio",authorized=True)
        ws.create_project("original_race","racing",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,values,token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if token:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(values),headers)
        response=conn.getresponse()
        status=response.status;payload=json.loads(response.read());conn.close()
        return status,payload

    def test_verified_studio_racer_project_download_and_tamper_rejection(self):
        cfg={"track_length":35}
        scene=make_advanced_scene("racing",cfg,seed=5)
        game=run_advanced_session("racing",cfg,
                ["accelerate","steer_left","coast"],seed=5,scene=scene)
        code,body=self.post("/api/advanced-godot-package",{
            "session":game,"settings":cfg})
        self.assertEqual(code,200)
        self.assertEqual(body["engine"],"racing")
        self.assertEqual(body["file_name"],"original-godot-racing.zip")
        self.assertFalse(body["source_project_mutated"])
        self.assertFalse(body["gameplay_native_verified_by_this_request"])
        payload=b64decode(body["zip_base64"],validate=True)
        self.assertEqual(sha256(payload).hexdigest(),body["zip_sha256"])
        with ZipFile(BytesIO(payload)) as z:
            self.assertIn("original-godot-racing/godot/scripts/main.gd",z.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":game},token=False)[0],403)
        bad=deepcopy(game);bad["state"]["championship_points"]=9999
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":bad,"settings":cfg})[0],400)

    def test_studio_whitelist_allows_race_but_not_unported_survival(self):
        html=render_workspace_html("D"*32).decode()
        self.assertIn('"tower_defense","racing","survival","farming"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)


if __name__=="__main__":
    unittest.main()
