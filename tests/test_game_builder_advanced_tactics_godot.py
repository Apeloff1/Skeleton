"""Independent Godot tactics gameplay, original maps, custody and studio export."""
from __future__ import annotations
from base64 import b64decode
from contextlib import redirect_stderr,redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import BytesIO,StringIO
from pathlib import Path
from zipfile import ZipFile
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_tactics_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_TACTICS,render_tactics_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


def authored_tactics(settings=None,seed=3,*,obstacles=None):
    settings=settings or {}
    layout={
        "obstacles":list(obstacles or []),
        "squad_spawns":[[0,0],[0,1]],
        "enemy_spawns":[[2,0],[2,1]],
        "objective":[3,3],
    }
    return make_advanced_scene("tactics",settings,seed=seed,layout=layout)


class NativeTacticsProofTests(unittest.TestCase):
    def test_source_exact_and_all_state_fields(self):
        cfg={"board_width":4,"board_height":4,"attack_range":4,"unit_health":8}
        scene=authored_tactics(cfg)
        actions=["guard","switch","overwatch","end_turn"]
        receipt=run_advanced_session("tactics",cfg,actions,seed=3,scene=scene)
        self.assertTrue(verify_advanced_session(receipt,cfg))
        package=render_tactics_godot_package(receipt,cfg,authorized=True)
        self.assertEqual(package.manifest["native_editor"],"tactics")
        self.assertEqual(package.manifest["native_adapter"],"godot4_independent_tactics")
        self.assertFalse(package.manifest["godot_executed"])
        self.assertFalse(package.manifest["publish_approved"])
        source=json.loads(package.files["godot/game.json"])
        proof=json.loads(package.files["godot/proof.json"])
        self.assertEqual(source["schema"],SCHEMA)
        self.assertEqual(proof["schema"],PROOF_SCHEMA)
        self.assertEqual(source["scene"],scene)
        self.assertEqual(proof["expected"],
                         {field:receipt["state"][field] for field in PROOF_FIELDS})
        self.assertEqual(proof["actions"],actions)
        self.assertEqual(package.files,render_tactics_godot_package(
            receipt,cfg,authorized=True).files)

    def test_real_authored_victory_and_objective_retained(self):
        cfg={"board_width":4,"board_height":4,"attack_range":4,"unit_health":4}
        scene=authored_tactics(cfg)
        win=run_advanced_session("tactics",cfg,["attack:0","attack:1"],
                                 seed=3,scene=scene)
        self.assertTrue(win["state"]["finished"])
        self.assertEqual(win["state"]["score"],200)
        self.assertEqual(win["state"]["enemies"],[])
        self.assertEqual(win["state"]["objective"],[3,3])
        package=render_tactics_godot_package(win,cfg,authorized=True)
        self.assertTrue(json.loads(package.files["godot/proof.json"])["expected"]["finished"])

    def test_actual_enemy_turns_overwatch_healing_and_switch(self):
        cfg={"board_width":4,"board_height":4,"attack_range":4,"unit_health":20}
        source=authored_tactics(cfg)
        cmds=["guard","heal","switch","overwatch","end_turn","switch",
              "east","end_turn"]
        receipt=run_advanced_session("tactics",cfg,cmds,seed=3,scene=source)
        self.assertEqual(receipt["state"]["round"],3)
        self.assertEqual(receipt["state"]["active_unit"],0)
        self.assertIn("overwatch_hit",[
            event for record in receipt["trace"] for event in record["events"]])
        pkg=render_tactics_godot_package(receipt,cfg,authorized=True)
        self.assertEqual(json.loads(pkg.files["godot/proof.json"])["actions"],cmds)

    def test_reject_wrong_session_tampering_and_overwrites(self):
        game=run_advanced_session("tactics",actions=["end_turn"])
        with self.assertRaises(PermissionError):
            render_tactics_godot_package(game,authorized=False)
        changed=deepcopy(game);changed["state"]["score"]=10000
        with self.assertRaises(AdvancedRuntimeError):
            render_tactics_godot_package(changed,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_tactics_godot_package(game,{"attack_range":10},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_tactics_godot_package(run_advanced_session("shooter"),authorized=True)
        package=render_tactics_godot_package(game,authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"squad-project"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,target,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                package,target,authorized=True),target)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,target,authorized=True)

    def test_deterministic_original_archive_and_rules_independent(self):
        game=run_advanced_session("tactics",actions=["guard","end_turn"])
        pkg=render_tactics_godot_package(game,authorized=True)
        data=archive_advanced_godot_package(pkg)
        self.assertEqual(data,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()),
                  {"original-godot-tactics/"+path for path in pkg.files})
            for path,blob in pkg.files.items():
                self.assertEqual(archive.read("original-godot-tactics/"+path),blob)
        for token in ("func _enemy_round(","func _line_clear(","func _step(",
                      "func _verify(", "overwatch_hit","direct_attack",
                      "enemy_advanced","NATIVE_ADVANCED_TACTICS_OK"):
            self.assertIn(token,GODOT_TACTICS)
        for forbidden in ("OS.execute(","HTTPRequest","HTTPClient","eval(",
                          "EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_TACTICS)

    def test_offline_cli_requires_authorization(self):
        receipt=run_advanced_session("tactics",actions=["guard"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            f=root/"session.json";f.write_text(json.dumps(receipt),encoding="utf-8")
            target=root/"original-tactics"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(f),
                                      "--output",str(target)]),2)
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(cli(["godot-export","--session",str(f),
                        "--output",str(target),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(out.getvalue())["native_editor"],"tactics")
            self.assertTrue((target/"godot/scripts/main.gd").is_file())


class TacticsStudioExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ws=GameWorkspace.create(Path(self.temp.name)/"workspace",authorized=True)
        ws.create_project("original_squad","tactics",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        t=threading.Thread(target=self.server.serve_forever,daemon=True)
        t.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,data,authenticated=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if authenticated:
            headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(data),headers)
        res=conn.getresponse()
        code=res.status;body=json.loads(res.read());conn.close()
        return code,body

    def test_source_bound_native_tactics_download(self):
        settings={"board_width":4,"board_height":4}
        scene=authored_tactics(settings)
        session=run_advanced_session("tactics",settings,["guard"],
                                      seed=3,scene=scene)
        status,payload=self.post("/api/advanced-godot-package",{
            "session":session,"settings":settings})
        self.assertEqual(status,200)
        self.assertEqual(payload["engine"],"tactics")
        self.assertEqual(payload["file_name"],"original-godot-tactics.zip")
        self.assertFalse(payload["source_project_mutated"])
        self.assertFalse(payload["gameplay_native_verified_by_this_request"])
        blob=b64decode(payload["zip_base64"],validate=True)
        self.assertEqual(sha256(blob).hexdigest(),payload["zip_sha256"])
        with ZipFile(BytesIO(blob)) as archive:
            self.assertIn("original-godot-tactics/godot/scripts/main.gd",archive.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":session},authenticated=False)[0],403)
        changed=deepcopy(session);changed["state"]["action_points"]=99
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":changed,"settings":settings})[0],400)

    def test_gated_native_game_ui(self):
        html=render_workspace_html("E"*32).decode()
        self.assertIn('"shooter","tactics","tower_defense"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)


if __name__=="__main__":
    unittest.main()
