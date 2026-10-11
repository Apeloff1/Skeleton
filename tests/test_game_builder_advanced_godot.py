"""Native Godot advanced-puzzle source package: exact independent replay custody."""
from __future__ import annotations

from hashlib import sha256
import io
from base64 import b64decode
import http.client
import json
import threading
from zipfile import ZipFile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, AdvancedRuntimeError,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene, SceneError
from skeleton.ai.game_builder.advanced_puzzle_solver import solve_advanced_puzzle
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError, NativeAdvancedGamePackage,
    render_advanced_godot_package, write_advanced_godot_package,
    archive_advanced_godot_package,
    GODOT_PUZZLE, NATIVE_SCHEMA, PROOF_SCHEMA,
)
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html


class AdvancedGodotPackageTests(unittest.TestCase):
    def make_win(self,mode="switches",seed=7):
        settings={"board_width":4,"board_height":4,"logic":mode}
        scene=make_advanced_scene("puzzle",settings,seed=seed)
        result=solve_advanced_puzzle(scene,settings)
        self.assertEqual(result["status"],"solved")
        self.assertTrue(result["verified_by_authoritative_replay"])
        session=run_advanced_session("puzzle",settings,
                  result["commands"],seed=seed,scene=scene)
        self.assertTrue(session["state"]["finished"])
        return settings,session

    def test_all_five_logic_modes_export_independent_native_gameplay(self):
        for mode in ("switches","push_blocks","circuits","time","non_euclidean"):
            with self.subTest(mode=mode):
                config,receipt=self.make_win(mode)
                package=render_advanced_godot_package(
                    receipt,config,authorized=True)
                self.assertIsInstance(package,NativeAdvancedGamePackage)
                self.assertEqual(package.manifest["native_editor"],"puzzle")
                self.assertFalse(package.manifest["godot_executed"])
                self.assertFalse(package.manifest["publish_approved"])
                self.assertIn(b"extends Control",package.files["godot/scripts/main.gd"])
                self.assertIn(b"func _step(",package.files["godot/scripts/main.gd"])
                self.assertIn(b"func _verify_advanced_proof(",package.files["godot/scripts/main.gd"])
                self.assertNotIn(b"load(\"https://",package.files["godot/scripts/main.gd"])
                proof=json.loads(package.files["godot/proof.json"])
                source=json.loads(package.files["godot/game.json"])
                self.assertEqual(source["schema"],NATIVE_SCHEMA)
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(proof["actions"],receipt["actions"])
                self.assertEqual(proof["expected"]["finished"],True)
                self.assertEqual(proof["expected"]["player"],receipt["state"]["player"])
                self.assertEqual(proof["python_session_digest"],receipt["digest"])
                self.assertEqual(proof["scene_digest"],receipt["scene_digest"])
                self.assertEqual(len(package.manifest["files"]),7)
                for name,expected in package.manifest["files"].items():
                    self.assertEqual(sha256(package.files[name]).hexdigest(),expected)
                repeated=render_advanced_godot_package(
                    receipt,config,authorized=True)
                self.assertEqual(package.files,repeated.files)

    def test_real_prefix_and_rewind_sessions_also_export(self):
        settings={"board_width":4,"board_height":4}
        scene=make_advanced_scene("puzzle",settings,seed=2)
        session=run_advanced_session("puzzle",settings,
                    ["east","undo","wait","east","interact"],seed=2,scene=scene)
        pkg=render_advanced_godot_package(session,settings,authorized=True)
        proof=json.loads(pkg.files["godot/proof.json"])
        self.assertFalse(proof["expected"]["finished"])
        self.assertEqual(proof["expected"]["tick"],5)
        self.assertEqual(proof["expected"]["undo_available"],31)
        self.assertEqual(pkg.manifest["source_session_digest"],session["digest"])

    def test_reject_forged_gameplay_unauthorized_calls_and_unported_genres(self):
        settings,game=self.make_win()
        with self.assertRaises(PermissionError):
            render_advanced_godot_package(game,settings,authorized=False)
        manipulated=dict(game)
        manipulated["actions"]=["wait"]
        with self.assertRaises(AdvancedRuntimeError):
            render_advanced_godot_package(manipulated,settings,authorized=True)
        with self.assertRaises(SceneError):
            render_advanced_godot_package(game,{"board_width":6},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_advanced_godot_package(
                run_advanced_session("racing"),authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_advanced_godot_package(
                run_advanced_session("shooter"),authorized=True)

    def test_atomic_no_overwrite_local_source_export(self):
        settings,game=self.make_win()
        package=render_advanced_godot_package(game,settings,authorized=True)
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"advanced_godot"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,destination,authorized=False)
            self.assertFalse(destination.exists())
            written=write_advanced_godot_package(package,destination,authorized=True)
            self.assertEqual(written,destination)
            self.assertEqual((destination/"release.json").read_bytes(),
                             package.files["release.json"])
            self.assertTrue((destination/"godot/project.godot").is_file())
            self.assertTrue((destination/"godot/scripts/main.gd").is_file())
            self.assertTrue((destination/"godot/scenes/main.tscn").is_file())
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,destination,authorized=True)

    def test_cli_real_native_export_needs_operator_and_existing_unique_path(self):
        cfg,game=self.make_win()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            receipt=path/"receipt.json"
            settings=path/"settings.json"
            receipt.write_text(json.dumps(game),encoding="utf-8")
            settings.write_text(json.dumps(cfg),encoding="utf-8")
            target=path/"native_output"
            with redirect_stderr(io.StringIO()):
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                    "--settings",str(settings),"--output",str(target)]),2)
            self.assertFalse(target.exists())
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                    "--settings",str(settings),"--output",str(target),
                    "--trusted-local-operator"]),0)
            result=json.loads(stdout.getvalue())
            self.assertEqual(result["local_output_path"],str(target))
            self.assertEqual(result["native_adapter"],"godot4_independent_puzzle")
            self.assertTrue((target/"godot/scripts/main.gd").is_file())

    def test_content_addressed_offline_native_zip_is_reproducible(self):
        settings,session=self.make_win("circuits")
        pkg=render_advanced_godot_package(session,settings,authorized=True)
        blob=archive_advanced_godot_package(pkg)
        self.assertEqual(blob,archive_advanced_godot_package(pkg))
        self.assertLess(len(blob),512000)
        with ZipFile(io.BytesIO(blob)) as archive:
            self.assertEqual(set(archive.namelist()),{
                "original-godot-puzzle/"+path for path in pkg.files})
            for path,data in pkg.files.items():
                self.assertEqual(archive.read("original-godot-puzzle/"+path),data)
        with self.assertRaises(AdvancedGodotExportError):
            archive_advanced_godot_package("unsafe")

    def test_pure_game_script_has_no_network_or_third_party_eval(self):
        for prohibited in ("HTTPClient","HTTPRequest","OS.execute","eval(",
                           "preload(\"res://addons", "EditorPlugin"):
            self.assertNotIn(prohibited,GODOT_PUZZLE)
        self.assertIn("NATIVE_ADVANCED_PUZZLE_OK",GODOT_PUZZLE)
        self.assertIn("match mode:",GODOT_PUZZLE)
        self.assertIn("JOY_BUTTON_DPAD_UP",GODOT_PUZZLE)


class NativeStudioDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ws=GameWorkspace.create(Path(self.temp.name)/"native-studio",authorized=True)
        ws.create_project("original_puzzle","puzzle",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.ws=ws

    def post(self,route,data,auth=True):
        conn=http.client.HTTPConnection("127.0.0.1",
                 self.server.server_port,timeout=10)
        headers={"Content-Type":"application/json"}
        if auth:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",route,json.dumps(data),headers)
        response=conn.getresponse()
        result=response.status,json.loads(response.read())
        conn.close()
        return result

    def test_local_puzzle_native_project_can_be_downloaded_but_not_forged(self):
        settings={"board_width":4,"board_height":4}
        scene=make_advanced_scene("puzzle",settings)
        receipt=run_advanced_session("puzzle",settings,
                                    ["east","interact"],scene=scene)
        status,payload=self.post("/api/advanced-godot-package",{
            "session":receipt,"settings":settings})
        self.assertEqual(status,200)
        self.assertEqual(payload["engine"],"puzzle")
        self.assertEqual(payload["file_name"],"original-godot-puzzle.zip")
        self.assertFalse(payload["source_project_mutated"])
        self.assertFalse(payload["gameplay_native_verified_by_this_request"])
        blob=b64decode(payload["zip_base64"],validate=True)
        self.assertEqual(sha256(blob).hexdigest(),payload["zip_sha256"])
        with ZipFile(io.BytesIO(blob)) as archive:
            source=json.loads(archive.read("original-godot-puzzle/godot/game.json"))
        self.assertEqual(source["scene"]["digest"],scene["digest"])
        self.assertFalse((self.ws.root/"current/original_puzzle/godot").exists())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":receipt,"settings":settings},auth=False)[0],403)
        tampered=dict(receipt)
        tampered["actions"]=["invalid"]
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":tampered,"settings":settings})[0],400)
        code,shooter=self.post("/api/advanced-godot-package",{
            "session":run_advanced_session("shooter")})
        self.assertEqual(code,200)
        self.assertEqual(shooter["engine"],"shooter")
        self.assertFalse(shooter["gameplay_native_verified_by_this_request"])
        code,source=self.post("/api/advanced-godot-package",{
            "session":run_advanced_session("racing")})
        self.assertEqual(code,200)
        self.assertEqual(source["engine"],"racing")
        self.assertFalse(source["gameplay_native_verified_by_this_request"])
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":run_advanced_session("survival")})[0],400)

    def test_visual_studio_handoff_controls_present(self):
        html=render_workspace_html("A"*32).decode()
        self.assertIn('id="advanced-godot-export"',html)
        self.assertIn("/api/advanced-godot-package",html)
        self.assertIn("Native Godot export requires a verified puzzle, platformer, deck battler, shooter, tactics, tower defense or racing session",html)
        self.assertIn("Content-Security-Policy",html)


if __name__=="__main__":
    unittest.main()
