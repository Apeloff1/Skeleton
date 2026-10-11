"""Original advanced arena shooter native gameplay, source and studio custody."""
from __future__ import annotations

from base64 import b64decode
from contextlib import redirect_stdout,redirect_stderr
from copy import deepcopy
from hashlib import sha256
from io import BytesIO,StringIO
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from zipfile import ZipFile

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session, AdvancedRuntimeError,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene, SceneError
from skeleton.ai.game_builder.advanced_shooter_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_SHOOTER,render_shooter_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli


class NativeArenaShooterProofTests(unittest.TestCase):
    def test_authoring_seeded_combat_and_replay_receipts(self):
        variants=(
            ({"player_health":60},["wait","east","east","cover"],2),
            ({"enemy_count":3,"player_health":90},
             ["dash:east","wait","wait","wait"],9),
            ({"enemy_count":1,"player_health":100,"dodge_charges":0},
             ["north","south","west","east","wait"],0),
        )
        for cfg,actions,seed in variants:
            with self.subTest(seed=seed):
                scene=make_advanced_scene("shooter",cfg,seed=seed)
                game=run_advanced_session("shooter",cfg,actions,seed=seed,scene=scene)
                self.assertTrue(verify_advanced_session(game,cfg))
                result=render_shooter_godot_package(game,cfg,authorized=True)
                self.assertEqual(result.manifest["native_editor"],"shooter")
                self.assertEqual(result.manifest["native_adapter"],"godot4_independent_shooter")
                self.assertTrue(result.manifest["advanced_floor"])
                self.assertFalse(result.manifest["godot_executed"])
                self.assertFalse(result.manifest["publish_approved"])
                expected={name:game["state"][name] for name in PROOF_FIELDS}
                proof=json.loads(result.files["godot/proof.json"])
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(proof["expected"],expected)
                self.assertEqual(proof["actions"],actions)
                self.assertEqual(proof["scene_digest"],scene["digest"])
                self.assertEqual(proof["python_session_digest"],game["digest"])
                self.assertEqual(json.loads(result.files["godot/game.json"])["schema"],SCHEMA)
                self.assertEqual(result.files,render_shooter_godot_package(
                    game,cfg,authorized=True).files)

    def test_authored_arena_firing_and_hostile_ai_are_not_placeholders(self):
        cfg={"enemy_count":3,"player_health":100,"weapon_damage":10}
        base=make_advanced_scene("shooter",cfg,seed=4)
        layout=deepcopy(base["layout"])
        layout["player_spawn"]=[8,4]
        layout["enemy_spawns"]=[[8,2],[10,4],[8,6]]
        scene=make_advanced_scene("shooter",cfg,seed=4,layout=layout)
        game=run_advanced_session("shooter",cfg,["fire","fire"],seed=4,scene=scene)
        self.assertGreater(game["state"]["defeated"],0)
        self.assertGreater(game["state"]["score"],0)
        self.assertEqual(game["state"]["ammo"],10)
        self.assertIn("weapon_hit",game["trace"][0]["events"])
        self.assertTrue(verify_advanced_session(game,cfg))
        result=render_shooter_godot_package(game,cfg,authorized=True)
        self.assertEqual(json.loads(result.files["godot/game.json"])["scene"],scene)

    def test_shooter_rejects_tampering_and_wrong_settings_and_unauthorized_writes(self):
        cfg={"player_health":30}
        game=run_advanced_session("shooter",cfg,["wait"])
        with self.assertRaises(PermissionError):
            render_shooter_godot_package(game,cfg,authorized=False)
        with self.assertRaises(AdvancedRuntimeError):
            render_shooter_godot_package(game,{"player_health":50},authorized=True)
        altered=deepcopy(game);altered["state"]["ammo"]=999
        with self.assertRaises(AdvancedRuntimeError):
            render_shooter_godot_package(altered,cfg,authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_shooter_godot_package(run_advanced_session("puzzle"),authorized=True)
        pkg=render_shooter_godot_package(game,cfg,authorized=True)
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/"original-arena"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(pkg,dst,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                pkg,dst,authorized=True),dst)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(pkg,dst,authorized=True)

    def test_distinct_fixed_original_zip_and_native_script_rules(self):
        receipt=run_advanced_session("shooter",actions=["east","wait"])
        pkg=render_shooter_godot_package(receipt,authorized=True)
        blob=archive_advanced_godot_package(pkg)
        self.assertEqual(blob,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(blob)) as z:
            self.assertEqual(set(z.namelist()),
                             {"original-godot-shooter/"+name for name in pkg.files})
            for path,body in pkg.files.items():
                self.assertEqual(z.read("original-godot-shooter/"+path),body)
        for required in ("func _spawn_wave(", "func _visible(", "func _step(",
                         "func _verify(", "weapon_hit","enemy_reinforcement_wave",
                         "enemy_patrolled","mission_extracted","NATIVE_ADVANCED_SHOOTER_OK"):
            self.assertIn(required,GODOT_SHOOTER)
        for forbidden in ("HTTPRequest","HTTPClient","OS.execute(", "eval(",
                          'load("https://',"EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_SHOOTER)

    def test_reviewed_local_cli_source_export(self):
        receipt=run_advanced_session("shooter",actions=["wait","east"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/"session.json"
            path.write_text(json.dumps(receipt))
            out=root/"game"
            with redirect_stderr(StringIO()):
                self.assertEqual(editor_cli(["godot-export","--session",str(path),
                    "--output",str(out)]),2)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(editor_cli(["godot-export","--session",str(path),
                    "--output",str(out),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(stdout.getvalue())["native_editor"],"shooter")
            self.assertTrue((out/"godot/scripts/main.gd").is_file())


class NativeShooterStudioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ws=GameWorkspace.create(Path(temp.name)/"arena-studio",authorized=True)
        ws.create_project("original_arena","shooter",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,route,data,token=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if token:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",route,json.dumps(data),headers)
        res=conn.getresponse();code=res.status;body=json.loads(res.read())
        conn.close()
        return code,body

    def test_token_gated_verified_shooter_game_download(self):
        scene=make_advanced_scene("shooter",seed=3)
        game=run_advanced_session("shooter",seed=3,scene=scene,actions=["east"])
        status,response=self.post("/api/advanced-godot-package",{"session":game})
        self.assertEqual(status,200)
        self.assertEqual(response["file_name"],"original-godot-shooter.zip")
        self.assertEqual(response["engine"],"shooter")
        self.assertFalse(response["source_project_mutated"])
        self.assertFalse(response["gameplay_native_verified_by_this_request"])
        data=b64decode(response["zip_base64"],validate=True)
        self.assertEqual(sha256(data).hexdigest(),response["zip_sha256"])
        with ZipFile(BytesIO(data)) as zip_file:
            self.assertIn("original-godot-shooter/godot/scripts/main.gd",
                          zip_file.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",
                                  {"session":game},token=False)[0],403)
        invalid=deepcopy(game);invalid["state"]["hp"]=300
        self.assertEqual(self.post("/api/advanced-godot-package",
                                  {"session":invalid})[0],400)

    def test_visual_export_lists_shooter_but_not_unported_genres(self):
        html=render_workspace_html("D"*32).decode()
        self.assertIn('"deck_battler","shooter","tactics","tower_defense","racing"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)
        self.assertIn("Content-Security-Policy",html)


if __name__=="__main__":
    unittest.main()
