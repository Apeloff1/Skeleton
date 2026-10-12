"""Real independent Godot 4 tower defense: authored waves, finite economy and replay."""
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
from skeleton.ai.game_builder.advanced_defense_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_DEFENSE,render_defense_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


class NativeTowerDefenseContractTests(unittest.TestCase):
    def test_economy_upgrade_sell_priorities_and_repeatable_native_package(self):
        config={"lane_length":12,"tower_damage":7,"tower_range":5}
        scene=make_advanced_scene("tower_defense",config,seed=9,layout={
            "build_slots":[0,2],"waves":2})
        commands=["build:0","upgrade:0","priority:strong","tick:4",
                  "priority:first","sell:0","build:2","tick"]
        receipt=run_advanced_session("tower_defense",config,commands,seed=9,scene=scene)
        self.assertTrue(verify_advanced_session(receipt,config))
        pkg=render_defense_godot_package(receipt,config,authorized=True)
        self.assertEqual(pkg.manifest["native_editor"],"tower_defense")
        self.assertEqual(pkg.manifest["native_adapter"],"godot4_independent_tower_defense")
        self.assertTrue(pkg.manifest["advanced_floor"])
        self.assertFalse(pkg.manifest["godot_executed"])
        self.assertFalse(pkg.manifest["publish_approved"])
        game=json.loads(pkg.files["godot/game.json"])
        proof=json.loads(pkg.files["godot/proof.json"])
        self.assertEqual(game["schema"],SCHEMA)
        self.assertEqual(proof["schema"],PROOF_SCHEMA)
        self.assertEqual(game["scene"],scene)
        self.assertEqual(proof["actions"],commands)
        self.assertEqual(proof["expected"],
                         {field:receipt["state"][field] for field in PROOF_FIELDS})
        self.assertEqual(pkg.files,render_defense_godot_package(
            receipt,config,authorized=True).files)

    def test_real_authored_wave_victory_and_failure(self):
        config={"lane_length":4,"wave_size":1,"tower_range":10,
                "tower_damage":10,"starting_credits":40}
        scene=make_advanced_scene("tower_defense",config,seed=0,
                                  layout={"build_slots":[0],"waves":1})
        win=run_advanced_session("tower_defense",config,
             ["build:0","tick:4"],seed=0,scene=scene)
        self.assertTrue(win["state"]["finished"])
        self.assertEqual(win["state"]["waves_completed"],1)
        self.assertEqual(win["state"]["defeated"],1)
        self.assertEqual(win["state"]["base_hp"],20)
        proof=render_defense_godot_package(win,config,authorized=True)
        self.assertTrue(json.loads(proof.files["godot/proof.json"])["expected"]["finished"])
        fail_cfg={"lane_length":4,"wave_size":3,"starting_credits":0}
        fail_scene=make_advanced_scene("tower_defense",fail_cfg,
                         layout={"build_slots":[0],"waves":12})
        lost=run_advanced_session("tower_defense",fail_cfg,
                       ["tick:4"]*6,scene=fail_scene)
        self.assertTrue(lost["state"]["failed"])
        self.assertEqual(lost["state"]["base_hp"],0)
        self.assertFalse(lost["state"]["finished"])
        self.assertTrue(render_defense_godot_package(lost,fail_cfg,authorized=True)
                        .manifest["advanced_floor"])

    def test_authored_slot_rejection_unchanged_in_source_contract(self):
        cfg={"starting_credits":80}
        scene=make_advanced_scene("tower_defense",cfg,layout={
            "build_slots":[2],"waves":1})
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("tower_defense",cfg,["build:0"],scene=scene)
        receipt=run_advanced_session("tower_defense",cfg,["build:2"],scene=scene)
        self.assertEqual(receipt["state"]["allowed_slots"],[2])
        self.assertEqual(receipt["state"]["towers"],[{"slot":2,"level":1}])

    def test_rejects_forged_session_untrusted_write_and_native_non_defense(self):
        receipt=run_advanced_session("tower_defense",actions=["tick"])
        with self.assertRaises(PermissionError):
            render_defense_godot_package(receipt,authorized=False)
        forged=deepcopy(receipt);forged["state"]["credits"]=100000
        with self.assertRaises(AdvancedRuntimeError):
            render_defense_godot_package(forged,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_defense_godot_package(receipt,{"wave_size":4},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_defense_godot_package(run_advanced_session("racing"),authorized=True)
        pkg=render_defense_godot_package(receipt,authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"original-tower"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(pkg,dest,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                pkg,dest,authorized=True),dest)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(pkg,dest,authorized=True)

    def test_byte_stable_offline_source_zip_and_independent_native_rules(self):
        receipt=run_advanced_session("tower_defense",actions=["tick","tick"])
        package=render_defense_godot_package(receipt,authorized=True)
        data=archive_advanced_godot_package(package)
        self.assertEqual(data,archive_advanced_godot_package(package))
        with ZipFile(BytesIO(data)) as z:
            self.assertEqual(set(z.namelist()),
                {"original-godot-tower_defense/"+path for path in package.files})
            for path,blob in package.files.items():
                self.assertEqual(z.read("original-godot-tower_defense/"+path),blob)
        for required in ("func _tick(", "func _step(", "func _verify(",
                         "enemy_escaped","tower_fired","tower_constructed",
                         "authored_waves_resolved","NATIVE_ADVANCED_DEFENSE_OK"):
            self.assertIn(required,GODOT_DEFENSE)
        for forbidden in ("HTTPClient","HTTPRequest","OS.execute(", "eval(",
                          "EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_DEFENSE)

    def test_verified_offline_cli_requires_explicit_operator(self):
        receipt=run_advanced_session("tower_defense",actions=["build:0"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);session=root/"session.json"
            session.write_text(json.dumps(receipt),encoding="utf-8")
            dest=root/"game"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(session),
                                      "--output",str(dest)]),2)
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(cli(["godot-export","--session",str(session),
                        "--output",str(dest),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(out.getvalue())["native_editor"],
                             "tower_defense")
            self.assertTrue((dest/"godot/project.godot").is_file())


class NativeDefenseStudioTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws=GameWorkspace.create(Path(tmp.name)/"defense-studio",authorized=True)
        ws.create_project("original_defense","tower_defense",authorized=True)
        self.server=create_workspace_server(ws,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,data,auth=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if auth:headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST",path,json.dumps(data),headers)
        res=conn.getresponse()
        status=res.status;body=json.loads(res.read());conn.close()
        return status,body

    def test_local_reviewed_game_zip_is_token_gated_and_non_mutating(self):
        cfg={"wave_size":2}
        scene=make_advanced_scene("tower_defense",cfg,seed=3,
                    layout={"build_slots":[1,2],"waves":2})
        receipt=run_advanced_session("tower_defense",cfg,["build:1","tick"],
                                     seed=3,scene=scene)
        code,body=self.post("/api/advanced-godot-package",{
            "session":receipt,"settings":cfg})
        self.assertEqual(code,200)
        self.assertEqual(body["engine"],"tower_defense")
        self.assertEqual(body["file_name"],"original-godot-tower_defense.zip")
        self.assertFalse(body["gameplay_native_verified_by_this_request"])
        self.assertFalse(body["source_project_mutated"])
        binary=b64decode(body["zip_base64"],validate=True)
        self.assertEqual(sha256(binary).hexdigest(),body["zip_sha256"])
        with ZipFile(BytesIO(binary)) as z:
            self.assertIn("original-godot-tower_defense/godot/scripts/main.gd",
                          z.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":receipt},auth=False)[0],403)
        forged=deepcopy(receipt);forged["state"]["base_hp"]=100
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":forged,"settings":cfg})[0],400)

    def test_gated_studio_export_allowlist_has_tower_defense(self):
        html=render_workspace_html("F"*32).decode()
        self.assertIn('"tactics","tower_defense","racing","survival","farming"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)


if __name__=="__main__":
    unittest.main()
