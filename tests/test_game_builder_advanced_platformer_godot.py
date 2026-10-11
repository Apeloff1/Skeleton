"""Actual Godot platformer adapter contracts, gameplay and studio source handoff."""
from __future__ import annotations

from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
import http.client
import json
from pathlib import Path
import tempfile
import threading
from contextlib import redirect_stdout, redirect_stderr
import unittest
from zipfile import ZipFile

from skeleton.ai.game_builder.advanced_platformer_godot import (
    SCHEMA, PROOF_SCHEMA, PROOF_FIELDS, GODOT_PLATFORMER,
    render_platformer_godot_package,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene, SceneError
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError, archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli


class OriginalPlatformerNativePackageTests(unittest.TestCase):
    def test_default_and_authored_gameplay_serialize_all_runtime_fields(self):
        scenarios=(
            ({"level_width":30},["right","jump_right","wait","dash_right"],2,None),
            ({"gravity":4,"run_speed":2,"double_jump":True},
             ["jump_right","jump_right","left","wait","right"],7,None),
            ({"level_width":16,"run_speed":1},["right","right","right","right"],3,
             {"spawn_x":0,"exit_x":15,"hazards":[5,7],"collectibles":[4,11],
              "checkpoints":[8,12]}),
        )
        for settings,commands,seed,layout in scenarios:
            with self.subTest(settings=settings):
                source=make_advanced_scene("platformer",settings,seed=seed,layout=layout)
                runtime=run_advanced_session("platformer",settings,commands,
                                             seed=seed,scene=source)
                self.assertTrue(verify_advanced_session(runtime,settings))
                pkg=render_platformer_godot_package(runtime,settings,authorized=True)
                self.assertEqual(pkg.manifest["native_adapter"],"godot4_independent_platformer")
                self.assertEqual(pkg.manifest["authored_scene_digest"],source["digest"])
                self.assertFalse(pkg.manifest["godot_executed"])
                self.assertFalse(pkg.manifest["native_hardware_certified"])
                self.assertFalse(pkg.manifest["publish_approved"])
                self.assertEqual(set(pkg.files),
                    set(pkg.manifest["files"])|{"release.json"})
                proof=json.loads(pkg.files["godot/proof.json"])
                game=json.loads(pkg.files["godot/game.json"])
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(game["schema"],SCHEMA)
                self.assertEqual(proof["expected"],
                                 {key:runtime["state"][key] for key in PROOF_FIELDS})
                self.assertEqual(proof["actions"],commands)
                self.assertEqual(game["scene"]["layout"],source["layout"])
                self.assertEqual(pkg.files,render_platformer_godot_package(
                    runtime,settings,authorized=True).files)

    def test_genuine_win_failure_checkpoint_and_double_jump_proofs(self):
        settings={"level_width":16,"run_speed":3,"gravity":3}
        scene=make_advanced_scene("platformer",settings,layout={
            "spawn_x":0,"exit_x":15,"hazards":[],
            "collectibles":[2,7],"checkpoints":[5,10]})
        winning=run_advanced_session("platformer",settings,["right"]*5,scene=scene)
        self.assertTrue(winning["state"]["finished"])
        self.assertEqual(winning["state"]["crystals"],[2,7])
        self.assertEqual(winning["state"]["checkpoint"],10)
        self.assertEqual(
            json.loads(render_platformer_godot_package(
                winning,settings,authorized=True).files["godot/proof.json"])["expected"]["finished"],True)
        jump=run_advanced_session("platformer",{"double_jump":True},
                                  ["jump_right","jump_right"])
        self.assertEqual(jump["state"]["air_jumps"],2)
        self.assertGreater(jump["state"]["y"],0)
        self.assertTrue(render_platformer_godot_package(
            jump,{"double_jump":True},authorized=True).manifest["advanced_floor"])

    def test_fail_closed_runtime_source_and_output_custody(self):
        source=make_advanced_scene("platformer")
        receipt=run_advanced_session("platformer",scene=source,actions=["right"])
        with self.assertRaises(PermissionError):
            render_platformer_godot_package(receipt,authorized=False)
        with self.assertRaises(AdvancedGodotExportError):
            render_platformer_godot_package(run_advanced_session("puzzle"),authorized=True)
        with self.assertRaises(SceneError):
            render_platformer_godot_package(receipt,{"level_width":25},authorized=True)
        tampered=deepcopy(receipt);tampered["state"]["health"]=999
        with self.assertRaises(AdvancedRuntimeError):
            render_platformer_godot_package(tampered,authorized=True)
        package=render_platformer_godot_package(receipt,authorized=True)
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"godot-platform"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,destination,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                package,destination,authorized=True),destination)
            self.assertTrue((destination/"godot/scripts/main.gd").is_file())
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,destination,authorized=True)

    def test_deterministic_source_archive_has_distinct_family_namespace(self):
        receipt=run_advanced_session("platformer",actions=["right"])
        pkg=render_platformer_godot_package(receipt,authorized=True)
        zipped=archive_advanced_godot_package(pkg)
        self.assertEqual(zipped,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(zipped)) as z:
            self.assertEqual(set(z.namelist()),
                             {"original-godot-platformer/"+name for name in pkg.files})
            for path,payload in pkg.files.items():
                self.assertEqual(z.read("original-godot-platformer/"+path),payload)

    def test_native_script_uses_separate_execution_logic_and_no_external_eval(self):
        for symbol in ("func _step(", "func _verify_proof(",
                       "hazard_respawn", "checkpoint_activated", "jump_impulse",
                       "dash_cooldown", "NATIVE_ADVANCED_PLATFORMER_OK",
                       "JOY_BUTTON_DPAD_LEFT"):
            self.assertIn(symbol,GODOT_PLATFORMER)
        for forbidden in ("OS.execute(", "HTTPClient", "HTTPRequest",
                          "eval(", "load(\"https://", "EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_PLATFORMER)

    def test_cli_can_export_real_native_game_under_explicit_authority(self):
        game=run_advanced_session("platformer",actions=["right","jump_right"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            receipt=root/"receipt.json";receipt.write_text(json.dumps(game))
            dest=root/"original-native-platformer"
            with redirect_stderr(StringIO()):
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                                              "--output",str(dest)]),2)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                    "--output",str(dest),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(stdout.getvalue())["native_editor"],"platformer")
            self.assertTrue((dest/"godot/proof.json").is_file())


class NativePlatformerStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ws=GameWorkspace.create(Path(self.temp.name)/"studio",authorized=True)
        ws.create_project("original_platformer","platformer",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def post(self,route,data,authorized=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if authorized:headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",route,json.dumps(data),headers)
        res=conn.getresponse()
        status=res.status;payload=json.loads(res.read())
        conn.close()
        return status,payload

    def test_verified_one_click_native_platform_game_and_unauthorized_denial(self):
        config={"level_width":16,"run_speed":1}
        scene=make_advanced_scene("platformer",config,seed=3)
        game=run_advanced_session("platformer",config,["jump_right","right"],seed=3,scene=scene)
        code,reply=self.post("/api/advanced-godot-package",{
            "session":game,"settings":config})
        self.assertEqual(code,200)
        self.assertEqual(reply["engine"],"platformer")
        self.assertEqual(reply["file_name"],"original-godot-platformer.zip")
        self.assertFalse(reply["gameplay_native_verified_by_this_request"])
        blob=b64decode(reply["zip_base64"],validate=True)
        self.assertEqual(sha256(blob).hexdigest(),reply["zip_sha256"])
        with ZipFile(BytesIO(blob)) as z:
            self.assertIn("original-godot-platformer/godot/scripts/main.gd",z.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":game,"settings":config},authorized=False)[0],403)
        forged=deepcopy(game);forged["state"]["finished"]=True
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":forged,"settings":config})[0],400)
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":run_advanced_session("racing")})[0],400)

    def test_visual_studio_has_native_download_control(self):
        html=render_workspace_html("B"*32).decode()
        self.assertIn("Download playable Godot 4 game project",html)
        self.assertIn('id="advanced-godot-export"',html)
        self.assertIn("puzzle\",\"platformer",html)
        self.assertIn("Content-Security-Policy",html)


if __name__=="__main__":
    unittest.main()
