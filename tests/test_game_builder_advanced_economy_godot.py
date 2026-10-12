"""Original market Godot native package, anti-forgery and Studio permission tests."""
from __future__ import annotations

from base64 import b64decode
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_economy_godot import (
    SCHEMA, PROOF_SCHEMA, PROOF_FIELDS, GODOT_ECONOMY,
    render_economy_godot_package,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError, archive_advanced_godot_package,
    write_advanced_godot_package,
)
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html

TRADE = ["audit", "manufacture", "focus:2", "buy", "travel:1",
         "audit", "sell", "checkpoint"]


class EconomyGodotPackageTests(unittest.TestCase):
    def test_independent_native_source_contains_real_mechanics(self):
        for marker in (
            "func _step(", "func _demand(", "func _verify(",
            "paid_finite_market_purchase", "market_paid_real_cargo_bid",
            "finite_regional_harvest", "material_conserving_original_manufacture",
            "verified_cross_market_delivery", "earned_nonterminal_trade_cooperation",
            "NATIVE_ADVANCED_ECONOMY_OK",
        ):
            self.assertIn(marker, GODOT_ECONOMY)
        for forbidden in ("HTTPRequest", "HTTPClient", "OS.execute(",
                          "eval(", "load('https://", "EditorPlugin"):
            self.assertNotIn(forbidden, GODOT_ECONOMY)

    def test_exact_source_full_state_projection_and_reproducible_package(self):
        for seed, actions in ((0, []), (1, TRADE),
                              (7, TRADE + ["retire"]),
                              (9, ["wait"] * 12),
                              (4, ["buy", "travel:1", "buy", "sell", "sell"])):
            with self.subTest(seed=seed):
                scene = make_advanced_scene("economy", seed=seed)
                proof = run_advanced_session("economy", actions=actions,
                                             seed=seed, scene=scene)
                self.assertTrue(verify_advanced_session(proof))
                package = render_economy_godot_package(proof, authorized=True)
                game = json.loads(package.files["godot/game.json"])
                expected = json.loads(package.files["godot/proof.json"])
                self.assertEqual(game["schema"], SCHEMA)
                self.assertEqual(expected["schema"], PROOF_SCHEMA)
                self.assertEqual(expected["actions"], actions)
                self.assertEqual(expected["scene_digest"], scene["digest"])
                self.assertEqual(expected["expected"], {
                    field: proof["state"][field] for field in PROOF_FIELDS
                })
                self.assertEqual(set(expected["expected"]), set(proof["state"]))
                self.assertFalse(package.manifest["godot_executed"])
                self.assertFalse(package.manifest["publish_approved"])
                self.assertEqual(package.manifest["native_editor"], "economy")
                self.assertEqual(package.files,
                    render_economy_godot_package(proof, authorized=True).files)
                self.assertEqual(sha256(package.files["godot/scripts/main.gd"]).hexdigest(),
                    package.manifest["files"]["godot/scripts/main.gd"])

    def test_original_layout_and_settings_change_native_source(self):
        a = run_advanced_session("economy", seed=1, actions=["inspect"])
        b = run_advanced_session("economy", seed=2, actions=["inspect"])
        pa = render_economy_godot_package(a, authorized=True)
        pb = render_economy_godot_package(b, authorized=True)
        self.assertNotEqual(pa.manifest["authored_scene_digest"],
                            pb.manifest["authored_scene_digest"])
        self.assertNotEqual(pa.files["godot/game.json"], pb.files["godot/game.json"])
        settings = {"goods": 3, "market_nodes": 2}
        custom = run_advanced_session("economy", settings, actions=["inspect"])
        pc = render_economy_godot_package(custom, settings, authorized=True)
        self.assertEqual(len(json.loads(pc.files["godot/game.json"])["scene"]
                             ["layout"]["markets"]), 2)

    def test_reject_forged_money_and_wrong_game_and_permission(self):
        session = run_advanced_session("economy", actions=TRADE)
        with self.assertRaises(PermissionError):
            render_economy_godot_package(session, authorized=False)
        with self.assertRaises(AdvancedGodotExportError):
            render_economy_godot_package(
                run_advanced_session("survival"), authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_economy_godot_package(
                session, {"trade_tax": 9}, authorized=True)
        for corrupt in (
            lambda x: x["state"].__setitem__("cash", 900000),
            lambda x: x["state"]["markets"][0].__setitem__("treasury", 900000),
            lambda x: x["state"].__setitem__("checkpoint", False),
            lambda x: x["actions"].append("retire"),
            lambda x: x["state"]["cargo_lots"][2].append(99),
        ):
            forged = deepcopy(session)
            corrupt(forged)
            with self.subTest(corrupt=corrupt):
                with self.assertRaises(AdvancedRuntimeError):
                    render_economy_godot_package(forged, authorized=True)

    def test_deterministic_zip_and_nonoverwriting_native_export(self):
        session = run_advanced_session("economy", actions=TRADE)
        package = render_economy_godot_package(session, authorized=True)
        zip1 = archive_advanced_godot_package(package)
        self.assertEqual(zip1, archive_advanced_godot_package(package))
        with ZipFile(BytesIO(zip1)) as archive:
            self.assertEqual(set(archive.namelist()),
                             {"original-godot-economy/" + path
                              for path in package.files})
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "original_economy"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package, target, authorized=False)
            self.assertEqual(write_advanced_godot_package(
                package, target, authorized=True), target)
            self.assertTrue((target/"godot/scripts/main.gd").is_file())
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package, target, authorized=True)

    def test_authorized_cli_creates_native_economy_project(self):
        session = run_advanced_session("economy", actions=TRADE)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)/"session.json"
            dst = Path(td)/"game"
            src.write_text(json.dumps(session), encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export", "--session", str(src),
                                      "--output", str(dst)]), 2)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(cli(["godot-export", "--session", str(src),
                    "--output", str(dst), "--trusted-local-operator"]), 0)
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["native_editor"], "economy")
            self.assertTrue((dst/"godot/game.json").exists())


class EconomyNativeStudioTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ws = GameWorkspace.create(Path(td.name)/"studio", authorized=True)
        ws.create_project("trading_world", "hybrid", authorized=True)
        server = create_workspace_server(ws, port=0)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def post(self, data, authorized=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port,
                                          timeout=8)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["X-Game-Studio-Token"] = self.server.secret
        conn.request("POST", "/api/advanced-godot-package",
                     json.dumps(data), headers=headers)
        response = conn.getresponse()
        status = response.status
        payload = json.loads(response.read())
        conn.close()
        return status, payload

    def test_real_native_economy_project_download_denies_untrusted_source(self):
        scene = make_advanced_scene("economy", seed=11)
        session = run_advanced_session("economy", actions=TRADE,
                                       seed=11, scene=scene)
        code, body = self.post({"session": session})
        self.assertEqual(code, 200)
        self.assertEqual(body["engine"], "economy")
        self.assertEqual(body["file_name"], "original-godot-economy.zip")
        self.assertFalse(body["source_project_mutated"])
        self.assertFalse(body["gameplay_native_verified_by_this_request"])
        archive = b64decode(body["zip_base64"], validate=True)
        self.assertEqual(body["zip_sha256"], sha256(archive).hexdigest())
        with ZipFile(BytesIO(archive)) as z:
            self.assertIn("original-godot-economy/godot/scripts/main.gd",
                          z.namelist())
        self.assertEqual(self.post({"session": session}, authorized=False)[0], 403)
        forged = deepcopy(session)
        forged["state"]["cash"] = 1_000_000
        self.assertEqual(self.post({"session": forged})[0], 400)

    def test_studio_offers_native_economy_only_for_verified_reference(self):
        html = render_workspace_html("x" * 32).decode("utf-8")
        self.assertIn('"factory","colony","economy"', html)
        self.assertIn("Download playable Godot 4 game project", html)
        self.assertIn('advancedSession.editor!=="economy"', html)


if __name__ == "__main__":
    unittest.main()
