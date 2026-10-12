"""Advanced native deck battler: real card mechanics and export custody."""
from __future__ import annotations

from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from zipfile import ZipFile
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_deck_godot import (
    SCHEMA,PROOF_SCHEMA,PROOF_FIELDS,GODOT_DECK_BATTLER,
    render_deck_godot_package,
)
from skeleton.ai.game_builder.advanced_genre_engines import CARDS
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,AdvancedRuntimeError,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,SceneError,
)
from skeleton.ai.game_builder.advanced_godot_export import (
    archive_advanced_godot_package,write_advanced_godot_package,
    AdvancedGodotExportError,
)
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.system_editor_cli import main as editor_cli


def themed_deck(card,seed=5,settings=None):
    settings=settings or {}
    cards=[card]*12
    if card not in {"strike","pierce","drain","spark"}:
        cards[-1]="strike"
    authored=make_advanced_scene("deck_battler",settings,seed=seed,layout={
        "cards":cards,"enemy_pattern":["attack","defend","poison","charge"],
        "hand_size":4,"enemy_armor":0,"potions":2,
    })
    return authored


class NativeDeckBattlerProofTests(unittest.TestCase):
    def test_eight_distinct_cards_generate_real_native_gameplay_rules(self):
        for card in sorted(CARDS):
            with self.subTest(card=card):
                scene=themed_deck(card)
                config={"enemy_health":100}
                # Authored settings must be exactly bound to the source digest.
                scene=themed_deck(card,settings=config)
                game=run_advanced_session("deck_battler",config,["play:0"],
                                          seed=scene["seed"],scene=scene)
                pkg=render_deck_godot_package(game,config,authorized=True)
                self.assertEqual(pkg.manifest["native_editor"],"deck_battler")
                self.assertEqual(pkg.manifest["native_adapter"],"godot4_independent_deck_battler")
                self.assertFalse(pkg.manifest["godot_executed"])
                self.assertFalse(pkg.manifest["publish_approved"])
                self.assertEqual(json.loads(pkg.files["godot/game.json"])["schema"],SCHEMA)
                proof=json.loads(pkg.files["godot/proof.json"])
                self.assertEqual(proof["schema"],PROOF_SCHEMA)
                self.assertEqual(proof["expected"],
                                 {key:game["state"][key] for key in PROOF_FIELDS})
                self.assertEqual(proof["scene_digest"],scene["digest"])
                self.assertEqual(proof["python_session_digest"],game["digest"])
                self.assertTrue(verify_advanced_session(game,config))
                self.assertEqual(pkg.files,render_deck_godot_package(
                    game,config,authorized=True).files)

    def test_energy_guard_enemy_status_poison_and_potion_are_playable(self):
        cfg={"enemy_health":90,"energy_per_turn":3}
        scene=themed_deck("guard",seed=5,settings=cfg)
        game=run_advanced_session("deck_battler",cfg,[
            "play:0","end_turn","end_turn","end_turn","potion",
            "end_turn","play:0","end_turn"],seed=5,scene=scene)
        self.assertGreater(game["state"]["round"],2)
        self.assertLess(game["state"]["potions"],2)
        self.assertTrue(verify_advanced_session(game,cfg))
        self.assertTrue(render_deck_godot_package(
            game,cfg,authorized=True).manifest["advanced_floor"])

    def test_boss_victory_and_terminal_game_cannot_be_replayed_further(self):
        cfg={"enemy_health":5,"attack_damage":10}
        scene=themed_deck("strike",settings=cfg)
        game=run_advanced_session("deck_battler",cfg,["play:0"],
                                  seed=scene["seed"],scene=scene)
        self.assertTrue(game["state"]["finished"])
        self.assertTrue(game["terminal"])
        self.assertEqual(game["state"]["enemy_hp"],0)
        pkg=render_deck_godot_package(game,cfg,authorized=True)
        self.assertTrue(json.loads(pkg.files["godot/proof.json"])["expected"]["finished"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("deck_battler",cfg,["play:0","end_turn"],
                                 seed=scene["seed"],scene=scene)

    def test_rounds_draw_exhaust_and_seeded_shuffle_are_deterministic(self):
        cfg={"enemy_health":100,"energy_per_turn":10,"attack_damage":1}
        scene=themed_deck("scry",seed=9,settings=cfg)
        commands=["play:0","end_turn","end_turn","end_turn","end_turn"]
        game=run_advanced_session("deck_battler",cfg,commands,seed=9,scene=scene)
        self.assertGreater(game["state"]["round"],4)
        self.assertTrue(verify_advanced_session(game,cfg))
        self.assertEqual(render_deck_godot_package(game,cfg,authorized=True).files,
             render_deck_godot_package(game,cfg,authorized=True).files)

    def test_source_verification_and_safe_portable_native_package(self):
        cfg={"enemy_health":20}
        scene=themed_deck("pierce",settings=cfg)
        game=run_advanced_session("deck_battler",cfg,["play:0"],seed=5,scene=scene)
        with self.assertRaises(PermissionError):
            render_deck_godot_package(game,cfg,authorized=False)
        forged=deepcopy(game);forged["state"]["enemy_hp"]=999
        with self.assertRaises(AdvancedRuntimeError):
            render_deck_godot_package(forged,cfg,authorized=True)
        with self.assertRaises(SceneError):
            render_deck_godot_package(game,{"enemy_health":25},authorized=True)
        with self.assertRaises(AdvancedGodotExportError):
            render_deck_godot_package(run_advanced_session("shooter"),authorized=True)
        package=render_deck_godot_package(game,cfg,authorized=True)
        archive=archive_advanced_godot_package(package)
        self.assertEqual(archive,archive_advanced_godot_package(package))
        with ZipFile(BytesIO(archive)) as zipfile:
            self.assertEqual(set(zipfile.namelist()),
                             {"original-godot-deck_battler/"+p for p in package.files})
            for path,contents in package.files.items():
                self.assertEqual(
                    zipfile.read("original-godot-deck_battler/"+path),contents)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"original-card-game"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package,target,authorized=False)
            self.assertEqual(write_advanced_godot_package(
                package,target,authorized=True),target)
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package,target,authorized=True)

    def test_godot_script_owns_logic_and_never_executes_external_code(self):
        for phrase in ("func _shuffle(", "func _draw_cards(", "func _step(",
                       "func _verify(", "enemy_poison_tick","potion_consumed",
                       "card_spark_played", "NATIVE_ADVANCED_DECK_OK",
                       "JOY_BUTTON_DPAD_LEFT"):
            if phrase=="card_spark_played":
                # Dynamic type-safe event prefix handles all registered cards.
                self.assertIn('"card_"+card+"_played"',GODOT_DECK_BATTLER)
            else:self.assertIn(phrase,GODOT_DECK_BATTLER)
        for danger in ("HTTPRequest","HTTPClient","OS.execute(", "eval(",
                       'load("https://', "EditorPlugin"):
            self.assertNotIn(danger,GODOT_DECK_BATTLER)

    def test_explicit_cli_review_and_authorization(self):
        game=run_advanced_session("deck_battler",actions=["end_turn"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=root/"session.json"
            receipt.write_text(json.dumps(game))
            target=root/"native-card-game"
            with redirect_stderr(StringIO()):
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                                   "--output",str(target)]),2)
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(editor_cli(["godot-export","--session",str(receipt),
                         "--output",str(target),"--trusted-local-operator"]),0)
            self.assertEqual(json.loads(captured.getvalue())["native_editor"],
                             "deck_battler")
            self.assertTrue((target/"godot/scripts/main.gd").is_file())


class NativeDeckStudioAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        workspace=GameWorkspace.create(Path(self.temp.name)/"studio",authorized=True)
        workspace.create_project("original_deck","deck_battler",authorized=True)
        self.server=create_workspace_server(workspace,port=0)
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
        code=response.status;payload=json.loads(response.read())
        conn.close()
        return code,payload

    def test_real_original_card_game_studio_zip_and_replay_denials(self):
        scene=make_advanced_scene("deck_battler",seed=2)
        game=run_advanced_session("deck_battler",["end_turn"] if False else None,
                                   actions=["end_turn"],seed=2,scene=scene)
        status,reply=self.post("/api/advanced-godot-package",{"session":game})
        self.assertEqual(status,200)
        self.assertEqual(reply["engine"],"deck_battler")
        self.assertEqual(reply["file_name"],"original-godot-deck_battler.zip")
        self.assertFalse(reply["gameplay_native_verified_by_this_request"])
        archive=b64decode(reply["zip_base64"],validate=True)
        self.assertEqual(sha256(archive).hexdigest(),reply["zip_sha256"])
        with ZipFile(BytesIO(archive)) as zipfile:
            self.assertIn("original-godot-deck_battler/godot/scripts/main.gd",
                          zipfile.namelist())
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":game},token=False)[0],403)
        tampered=deepcopy(game);tampered["state"]["hp"]=100
        self.assertEqual(self.post("/api/advanced-godot-package",{
            "session":tampered})[0],400)

    def test_local_studio_one_click_native_card_source_control(self):
        rendered=render_workspace_html("C"*32).decode()
        self.assertIn("Download playable Godot 4 game project",rendered)
        self.assertIn('id="advanced-godot-export"',rendered)
        self.assertIn('"deck_battler","shooter","tactics","tower_defense","racing","survival","farming","factory"].includes(advancedSession.editor)',rendered)


if __name__=="__main__":
    unittest.main()
