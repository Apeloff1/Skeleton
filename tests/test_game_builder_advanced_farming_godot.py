"""Ninth original advanced gameplay family: farming reference/native parity."""
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
    ENGINES,AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,validate_advanced_scene,SceneError,
)
from skeleton.ai.game_builder.advanced_farming_runtime import (
    ACTIONS,FarmingActionError,default_layout,normalize_layout,
)
from skeleton.ai.game_builder.advanced_farming_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_FARMING,render_farming_godot_package,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editor_cli import main as cli


def designed_farm(cfg=None,seed=0):
    cfg=cfg or {}
    return make_advanced_scene("farming",cfg,seed=seed,layout={
        "plots":[{"id":i,"soil":5,"moisture":5}
                 for i in range(min(4,cfg.get("field_tiles",4)))],
        "market_multiplier":2,
        "starting_weather":"rain",
    })


class FarmingReferenceAndNativeTests(unittest.TestCase):
    def test_real_reference_registration_and_replay(self):
        self.assertIn("farming",ENGINES)
        self.assertEqual(len(ACTIONS),27)
        for seed in (0,1,2,8):
            cfg={"crop_types":3,"field_tiles":4}
            source=designed_farm(cfg,seed)
            actions=["plant:0","plant:1","advance",
                     "advance:4","harvest:1","sell"]
            game=run_advanced_session("farming",cfg,actions,seed=seed,scene=source)
            self.assertTrue(verify_advanced_session(game,cfg))
            self.assertEqual(game["editor"],"farming")
            self.assertEqual(game["validated_turn_count"],len(actions))
            self.assertGreater(game["state"]["coins"],25)
            self.assertEqual(game["state"]["contracts_completed"],1)
            package=render_farming_godot_package(game,cfg,authorized=True)
            proof=json.loads(package.files["godot/proof.json"])
            self.assertEqual(proof["schema"],PROOF_SCHEMA)
            self.assertEqual(proof["expected"],{
                field:game["state"][field] for field in PROOF_FIELDS})
            self.assertEqual(json.loads(package.files["godot/game.json"])["schema"],SCHEMA)
            self.assertEqual(package.manifest["native_editor"],"farming")
            self.assertEqual(package.manifest["native_adapter"],"godot4_independent_farming")
            self.assertFalse(package.manifest["godot_executed"])
            self.assertEqual(package.files,render_farming_godot_package(
                game,cfg,authorized=True).files)

    def test_profitable_original_farm_requires_two_real_sales(self):
        cfg={"growth_days":2,"field_tiles":4,"crop_types":4,"livestock":False}
        scene=designed_farm(cfg)
        actions=["plant:0","plant:1","plant:2","plant:3","advance",
                 "harvest:0","harvest:1","harvest:2","harvest:3","sell",
                 "plant:0","plant:1","plant:2","plant:3","advance",
                 "harvest:0","harvest:1","harvest:2","harvest:3","sell"]
        game=run_advanced_session("farming",cfg,actions,scene=scene)
        self.assertTrue(game["terminal"])
        self.assertTrue(game["state"]["finished"])
        self.assertEqual(game["state"]["contracts_completed"],2)
        self.assertGreaterEqual(game["state"]["coins"],80)
        self.assertGreaterEqual(game["state"]["harvested"],8)
        self.assertIn("profitable_farm_established",game["state"]["events"])
        self.assertEqual(render_farming_godot_package(
            game,cfg,authorized=True).manifest["native_adapter"],
            "godot4_independent_farming")

    def test_planting_without_seeds_or_harvesting_unripe_is_rejected(self):
        cfg={"growth_days":15,"field_tiles":1}
        scene=designed_farm(cfg)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("farming",cfg,["harvest:0"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("farming",cfg,["plant:3"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("farming",cfg,["plant:0","plant:0"],scene=scene)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("farming",cfg,["plant:0","advance","harvest:0"],scene=scene)

    def test_authored_scene_rejects_extra_fields_unbounded_plot_or_noninteger(self):
        cfg={"field_tiles":4}
        source=designed_farm(cfg)
        self.assertEqual(validate_advanced_scene(source,cfg),source)
        bad=deepcopy(source)
        bad["layout"]["plots"][0]["soil"]=999
        with self.assertRaises(SceneError):
            make_advanced_scene("farming",cfg,layout=bad["layout"])
        bad=deepcopy(source);bad["layout"]["plots"][0]["soil"]=True
        with self.assertRaises(SceneError):
            make_advanced_scene("farming",cfg,layout=bad["layout"])
        bad=deepcopy(source);bad["layout"]["unexpected"]="unsafe"
        with self.assertRaises(SceneError):
            make_advanced_scene("farming",cfg,layout=bad["layout"])
        forged=deepcopy(source);forged["layout"]["plots"][0]["soil"]=0
        with self.assertRaises(SceneError):
            validate_advanced_scene(forged,cfg)

    def test_weather_growing_irrigation_and_livestock_are_actual_events(self):
        cfg={"field_tiles":4,"growth_days":4,"livestock":True}
        scene=designed_farm(cfg)
        layout=deepcopy(scene["layout"])
        layout["plots"][0]["soil"]=3
        scene=make_advanced_scene("farming",cfg,layout=layout)
        moves=["plant:0","plant:1","advance:4","collect",
               "irrigate","buy_seeds","compost:0","sell"]
        game=run_advanced_session("farming",cfg,moves,scene=scene)
        events=[e for step in game["trace"] for e in step["events"]]
        for event in ("crop_grew","livestock_produced","animal_products_collected",
                      "field_irrigated","seeds_purchased","soil_composted",
                      "genuine_harvest_sold"):
            self.assertIn(event,events)
        self.assertGreaterEqual(game["state"]["livestock"],2)
        self.assertTrue(verify_advanced_session(game,cfg))

    def test_source_custody_no_overwrite_forgeries_and_deterministic_zip(self):
        receipt=run_advanced_session("farming",actions=["plant:0","advance"])
        with self.assertRaises(PermissionError):
            render_farming_godot_package(receipt,authorized=False)
        forged=deepcopy(receipt);forged["state"]["coins"]=900000
        with self.assertRaises(AdvancedRuntimeError):
            render_farming_godot_package(forged,authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_farming_godot_package(receipt,{"field_tiles":2},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_farming_godot_package(run_advanced_session("survival"),authorized=True)
        package=render_farming_godot_package(receipt,authorized=True)
        zipped=archive_advanced_godot_package(package)
        self.assertEqual(zipped,archive_advanced_godot_package(package))
        with ZipFile(BytesIO(zipped)) as z:
            self.assertEqual(set(z.namelist()),
                             {"original-godot-farming/"+p for p in package.files})
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"farming"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,target,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                package,target,authorized=True),target)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,target,authorized=True)

    def test_real_native_rules_not_web_code_or_state_animation(self):
        for required in ("func _advance_day(", "func _step(", "func _verify(",
                         "livestock_hungry","profitable_farm_established",
                         "market_contract_fulfilled","crop_grew",
                         "mature_crop_harvested","NATIVE_ADVANCED_FARMING_OK"):
            self.assertIn(required,GODOT_FARMING)
        for forbidden in ("HTTPRequest","HTTPClient","OS.execute(", "eval(",
                          "EditorPlugin"):
            self.assertNotIn(forbidden,GODOT_FARMING)

    def test_authorized_cli_writes_real_native_source(self):
        session=run_advanced_session("farming",actions=["plant:0","advance"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/"session.json"
            p.write_text(json.dumps(session),encoding="utf-8")
            dest=root/"game"
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export","--session",str(p),
                                      "--output",str(dest)]),2)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(cli(["godot-export","--session",str(p),
                     "--output",str(dest),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(stdout.getvalue())["native_editor"],"farming")
            self.assertTrue((dest/"godot/scripts/main.gd").is_file())


class NativeFarmingStudioTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws=GameWorkspace.create(Path(tmp.name)/"studio",authorized=True)
        ws.create_project("original_farm","farming",authorized=True)
        self.server=create_workspace_server(ws,port=0)
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
        content=json.loads(response.read());conn.close()
        return status,content

    def test_original_authored_farm_studio_download_with_integrity(self):
        config={"field_tiles":4}
        scene=designed_farm(config)
        game=run_advanced_session("farming",config,
              ["plant:0","advance"],scene=scene)
        status,body=self.post({"session":game,"settings":config})
        self.assertEqual(status,200)
        self.assertEqual(body["engine"],"farming")
        self.assertEqual(body["file_name"],"original-godot-farming.zip")
        self.assertFalse(body["gameplay_native_verified_by_this_request"])
        self.assertFalse(body["source_project_mutated"])
        raw=b64decode(body["zip_base64"],validate=True)
        self.assertEqual(sha256(raw).hexdigest(),body["zip_sha256"])
        with ZipFile(BytesIO(raw)) as z:
            self.assertIn("original-godot-farming/godot/scripts/main.gd",z.namelist())
        self.assertEqual(self.post({"session":game},authorized=False)[0],403)
        forged=deepcopy(game);forged["state"]["harvested"]=90
        self.assertEqual(self.post({"session":forged,"settings":config})[0],400)

    def test_visual_studio_supports_nine_native_game_families(self):
        html=render_workspace_html("G"*32).decode()
        self.assertIn('"survival","farming"].includes(advancedSession.editor)',html)
        self.assertIn("Download playable Godot 4 game project",html)


if __name__=="__main__":
    unittest.main()
