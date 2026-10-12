"""Tenth original playable factory, canonical machine scenes and native custody."""
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
    AdvancedRuntimeError,ENGINES,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_factory_runtime import ROLES,ACTIONS
from skeleton.ai.game_builder.advanced_factory_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_FACTORY,render_factory_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


def original_factory(settings=None,seed=0,*,target=8,ore=40,coal=12,
                     market=3,stations=3):
    cfg=settings or {}
    return make_advanced_scene("factory",cfg,seed=seed,layout={
        "stations":[{"id":i,"role":ROLES[i]} for i in range(stations)],
        "ore_deposit":ore,"coal_deposit":coal,
        "market_price":market,"contract_target":target,
    })


class FactoryReferenceAndNativeContractTests(unittest.TestCase):
    def test_real_reference_engine_and_complete_native_state_receipt(self):
        self.assertIn("factory",ENGINES)
        self.assertGreater(len(ACTIONS),20)
        for seed in (0,3,7):
            cfg={"belt_speed":2,"machines":4,"recipes":4}
            scene=original_factory(cfg,seed)
            actions=["build:0","build:1","build:2","tick:4",
                     "mine","priority:speed","tick:4","ship"]
            game=run_advanced_session("factory",cfg,actions,seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(game,cfg))
            self.assertGreater(game["state"]["shipped"],0)
            self.assertEqual(game["editor"],"factory")
            package=render_factory_godot_package(game,cfg,authorized=True)
            self.assertEqual(package.manifest["native_editor"],"factory")
            self.assertEqual(package.manifest["native_adapter"],
                             "godot4_independent_factory")
            self.assertFalse(package.manifest["godot_executed"])
            self.assertFalse(package.manifest["publish_approved"])
            proof=json.loads(package.files["godot/proof.json"])
            self.assertEqual(proof["schema"],PROOF_SCHEMA)
            self.assertEqual(proof["actions"],actions)
            self.assertEqual(proof["expected"],
                {field:game["state"][field] for field in PROOF_FIELDS})
            self.assertEqual(json.loads(package.files["godot/game.json"])["schema"],SCHEMA)
            self.assertEqual(package.files,render_factory_godot_package(
                game,cfg,authorized=True).files)

    def test_real_three_stage_manufacturing_and_contract_win(self):
        cfg={"machines":4,"belt_speed":3,"power_supply":250}
        scene=original_factory(cfg,0)
        commands=["build:0","build:1","build:2",
                  "tick:4","ship","mine","mine","mine","tick:4","ship"]
        game=run_advanced_session("factory",cfg,commands,scene=scene)
        self.assertTrue(game["terminal"])
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(game["state"]["shipped"],8)
        self.assertEqual(game["state"]["contracts"],2)
        self.assertEqual(game["state"]["components"],0)
        self.assertIn("sustainable_factory_operating",game["state"]["events"])
        package=render_factory_godot_package(game,cfg,authorized=True)
        self.assertTrue(json.loads(package.files["godot/proof.json"])["expected"]["finished"])

    def test_energy_budget_pollution_scrubbing_upgrades_and_factory_repairs(self):
        cfg={"belt_speed":3,"power_supply":14,"pollution":True}
        scene=original_factory(cfg,0,stations=4)
        cmds=["build:0","build:1","build:2","build:3","priority:speed",
              "tick:4","generate","scrub","repair:0","buy_coal",
              "upgrade:0","toggle:3","toggle:3"]
        game=run_advanced_session("factory",cfg,cmds,scene=scene)
        events=[event for trace in game["trace"] for event in trace["events"]]
        for event in ("machine_constructed","production_priority_changed",
                      "machine_produced","pollution_scrubbed","machine_repaired",
                      "machine_upgraded","machine_switched","finite_coal_bought"):
            self.assertIn(event,events)
        self.assertEqual(game["state"]["maintenance"],1)
        self.assertEqual(game["state"]["mode"],"speed")
        self.assertTrue(verify_advanced_session(game,cfg))

    def test_unauthorized_or_impossible_materials_do_not_create_value(self):
        cfg={"machines":1,"belt_speed":3}
        scene=original_factory(cfg,stations=1,ore=1)
        for commands in (["ship"],["build:3"],["upgrade:0"],["repair:0"],
                         ["tick","generate"],["build:0","build:0"],
                         ["mine","mine"]):
            with self.subTest(actions=commands):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("factory",cfg,commands,scene=scene)
        session=run_advanced_session("factory",cfg,["build:0","mine"],scene=scene)
        self.assertEqual(session["state"]["ore_deposit"],0)
        self.assertEqual(session["state"]["ore"],11)

    def test_scene_strict_slot_identity_and_finite_deposits(self):
        cfg={"machines":3}
        scene=original_factory(cfg,stations=3)
        self.assertEqual(validate_advanced_scene(scene,cfg),scene)
        for patch in (
            lambda obj:obj["stations"][0].update({"role":"internet"}),
            lambda obj:obj["stations"][1].update({"id":0}),
            lambda obj:obj.update({"ore_deposit":-1}),
            lambda obj:obj.update({"contract_target":81}),
            lambda obj:obj.update({"extra_command":"eval"}),
            lambda obj:obj["stations"].append({"id":3,"role":"generator"}),
        ):
            with self.subTest(patch=repr(patch)):
                bad=deepcopy(scene["layout"]);patch(bad)
                with self.assertRaises(SceneError):
                    make_advanced_scene("factory",cfg,layout=bad)
        tampered=deepcopy(scene);tampered["layout"]["ore_deposit"]=90000
        with self.assertRaises(SceneError):
            validate_advanced_scene(tampered,cfg)

    def test_forgery_stale_settings_atomic_no_overwrite_and_zip_bytes(self):
        game=run_advanced_session("factory",actions=["build:0","tick"])
        with self.assertRaises(PermissionError):
            render_factory_godot_package(game,authorized=False)
        changed=deepcopy(game);changed["state"]["credits"]=99999
        with self.assertRaises(AdvancedRuntimeError):
            render_factory_godot_package(changed,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_factory_godot_package(game,{"belt_speed":5},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_factory_godot_package(run_advanced_session("farming"),authorized=True)
        pkg=render_factory_godot_package(game,authorized=True)
        data=archive_advanced_godot_package(pkg)
        self.assertEqual(data,archive_advanced_godot_package(pkg))
        with ZipFile(BytesIO(data)) as z:
            self.assertEqual(set(z.namelist()),
                {"original-godot-factory/"+path for path in pkg.files})
            for path,blob in pkg.files.items():
                self.assertEqual(z.read("original-godot-factory/"+path),blob)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"factory-game"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(pkg,path,authorized=False)
            self.assertEqual(write_advanced_godot_package(pkg,path,authorized=True),path)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(pkg,path,authorized=True)

    def test_real_native_rules_and_no_network_or_shell_execution(self):
        for needed in ("func _tick(", "func _step(", "func _verify(",
                       "manufacturing_contract_shipped","sustainable_factory_operating",
                       "finite_ore_mined","pollution_shutdown","machine_produced",
                       "machine_stalled","NATIVE_ADVANCED_FACTORY_OK"):
            self.assertIn(needed,GODOT_FACTORY)
        for forbidden in ("OS.execute(","HTTPRequest","HTTPClient","eval(",
                          "EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_FACTORY)

    def test_explicit_operator_only_cli_exports_project(self):
        game=run_advanced_session("factory",actions=["build:0","mine"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"game.json";source.write_text(json.dumps(game))
            dest=root/"original-factory"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(source),
                                      "--output",str(dest)]),2)
            with redirect_stdout(StringIO()) as result:
                self.assertEqual(cli(["godot-export","--session",str(source),
                    "--output",str(dest),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(result.getvalue())["native_editor"],"factory")
            self.assertTrue((dest/"godot/scripts/main.gd").is_file())


class FactoryStudioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        workspace=GameWorkspace.create(Path(temp.name)/"studio",authorized=True)
        workspace.create_project("original_factory","factory",authorized=True)
        self.server=create_workspace_server(workspace,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,data,authorized=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Content-Type":"application/json"}
        if authorized:headers["X-Game-Studio-Token"]=self.server.secret
        conn.request("POST","/api/advanced-godot-package",json.dumps(data),headers)
        response=conn.getresponse();status=response.status
        body=json.loads(response.read());conn.close()
        return status,body

    def test_verified_original_machine_game_download_does_not_change_project(self):
        cfg={"belt_speed":2}
        scene=original_factory(cfg,seed=1)
        game=run_advanced_session("factory",cfg,
                   ["build:0","build:1","mine","tick"],seed=1,scene=scene)
        status,payload=self.post({"session":game,"settings":cfg})
        self.assertEqual(status,200)
        self.assertEqual(payload["engine"],"factory")
        self.assertEqual(payload["file_name"],"original-godot-factory.zip")
        self.assertFalse(payload["source_project_mutated"])
        self.assertFalse(payload["gameplay_native_verified_by_this_request"])
        zipped=b64decode(payload["zip_base64"],validate=True)
        self.assertEqual(sha256(zipped).hexdigest(),payload["zip_sha256"])
        with ZipFile(BytesIO(zipped)) as z:
            self.assertIn("original-godot-factory/godot/scripts/main.gd",z.namelist())
        self.assertEqual(self.post({"session":game},authorized=False)[0],403)
        changed=deepcopy(game);changed["state"]["ore"]=99999
        self.assertEqual(self.post({"session":changed,"settings":cfg})[0],400)

    def test_original_game_studio_native_allowlist_now_ten(self):
        page=render_workspace_html("F"*32).decode()
        self.assertIn('"farming","factory"].includes(advancedSession.editor)',page)
        self.assertIn("Download playable Godot 4 game project",page)


if __name__=="__main__":
    unittest.main()
