"""Independent native Dialogue source evidence and explicit operator custody."""
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

from skeleton.ai.game_builder.advanced_dialogue_godot import (
    SCHEMA, PROOF_SCHEMA, PROOF_FIELDS, GODOT_DIALOGUE,
    render_dialogue_godot_package,
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

CONSENSUS = ("speak:0", "support:0", "travel:1", "speak:4",
             "travel:2", "compare:0", "claim")


class NativeOriginalDialogueTests(unittest.TestCase):
    def test_godot_contains_an_independent_world_not_a_precomputed_achievement(self):
        for marker in (
            "func _action(", "func _remember(", "func _decay(",
            "func _verify(", "func _canonical_number(",
            "player_traveled_to_original_social_station",
            "original_direct_testimony_heard_at_real_position",
            "finite_cost_original_support_raised_real_trust",
            "finite_cost_original_challenge_with_social_consequence",
            "original_two_independent_direct_speaker_sources_compared",
            "earned_original_social_consensus_nonterminal",
            "NATIVE_ADVANCED_DIALOGUE_OK",
        ):
            self.assertIn(marker, GODOT_DIALOGUE)
        for forbidden in (
            "HTTPRequest", "HTTPClient", "OS.execute(", "eval(",
            "load('https://", "load(\"https://", "EditorPlugin"
        ):
            self.assertNotIn(forbidden, GODOT_DIALOGUE)

    def test_deterministic_full_source_state_for_eight_original_social_scenarios(self):
        cases = (
            ("empty", {}, [], 0),
            ("consensus", {}, list(CONSENSUS), 2),
            ("retired", {}, list(CONSENSUS) + ["retire"], 2),
            ("challenge", {}, ["speak:0", "challenge:0", "wait", "rest"], 3),
            ("speech_and_travel", {}, ["travel:1", "speak:1",
                                       "travel:2", "speak:2", "travel:1",
                                       "travel:0", "speak:3"], 5),
            ("decay", {"memory_turns": 2}, ["speak:0", "wait", "wait", "wait"], 7),
            ("sparse", {"speakers": 500, "active_speakers_budget": 3},
                       ["speak:0", "support:0"], 10),
            ("silent", {"memory_turns": 0, "choice_consequences": False},
                       ["speak:0", "inspect"], 12),
        )
        for name, settings, actions, seed in cases:
            with self.subTest(name=name):
                scene = make_advanced_scene("dialogue", settings, seed=seed)
                receipt = run_advanced_session("dialogue", settings, actions,
                                               seed=seed, scene=scene)
                self.assertTrue(verify_advanced_session(receipt, settings))
                package = render_dialogue_godot_package(
                    receipt, settings, authorized=True)
                native = json.loads(package.files["godot/game.json"])
                proof = json.loads(package.files["godot/proof.json"])
                self.assertEqual(native["schema"], SCHEMA)
                self.assertEqual(proof["schema"], PROOF_SCHEMA)
                self.assertEqual(proof["scene_digest"], scene["digest"])
                self.assertEqual(proof["actions"], actions)
                self.assertEqual(proof["expected"], receipt["state"])
                self.assertEqual(set(proof["expected"]), set(PROOF_FIELDS))
                self.assertFalse(package.manifest["godot_executed"])
                self.assertFalse(package.manifest["publish_approved"])
                self.assertEqual(package.manifest["native_editor"], "dialogue")
                self.assertEqual(package.files,
                    render_dialogue_godot_package(
                        receipt, settings, authorized=True).files)
                for path, source_digest in package.manifest["files"].items():
                    self.assertEqual(sha256(package.files[path]).hexdigest(),
                                     source_digest)
                if name == "consensus":
                    self.assertTrue(receipt["state"]["checkpoint"])
                if name == "retired":
                    self.assertTrue(receipt["state"]["finished"])
                if name == "silent":
                    self.assertEqual(receipt["state"]["history"], [])
                if name == "sparse":
                    self.assertEqual(receipt["state"]["unmodeled_speakers"], 497)

    def test_authenticated_source_bound_custody_rejects_forged_consent_and_witnesses(self):
        scene = make_advanced_scene("dialogue", seed=2)
        receipt = run_advanced_session("dialogue", actions=CONSENSUS,
                                       seed=2, scene=scene)
        with self.assertRaises(PermissionError):
            render_dialogue_godot_package(receipt, authorized=False)
        with self.assertRaises(AdvancedGodotExportError):
            render_dialogue_godot_package(
                run_advanced_session("economy"), authorized=True)
        with self.assertRaises(AdvancedRuntimeError):
            render_dialogue_godot_package(
                receipt, {"support_cost": 8}, authorized=True)
        for tamper in (
            lambda s: s["state"]["speakers"][0].__setitem__("trust", 100),
            lambda s: s["state"]["direct_statements"][0].__setitem__("speaker", 7),
            lambda s: s["state"].__setitem__("checkpoint", False),
            lambda s: s["state"].__setitem__("influence", 99999),
            lambda s: s["actions"].append("retire"),
            lambda s: s["state"]["choices"][0].__setitem__("cost", 0),
        ):
            forged = deepcopy(receipt)
            tamper(forged)
            with self.subTest(tamper=tamper):
                with self.assertRaises(AdvancedRuntimeError):
                    render_dialogue_godot_package(forged, authorized=True)

    def test_zip_is_deterministic_and_export_cannot_overwrite_existing_source(self):
        receipt = run_advanced_session("dialogue", actions=CONSENSUS)
        package = render_dialogue_godot_package(receipt, authorized=True)
        payload = archive_advanced_godot_package(package)
        self.assertEqual(payload, archive_advanced_godot_package(package))
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(set(archive.namelist()),
                {"original-godot-dialogue/" + name for name in package.files})
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "native-original-dialogue"
            with self.assertRaises(PermissionError):
                write_advanced_godot_package(package, dest, authorized=False)
            self.assertEqual(
                write_advanced_godot_package(package, dest, authorized=True), dest)
            self.assertTrue((dest / "godot/scripts/main.gd").is_file())
            with self.assertRaises(AdvancedGodotExportError):
                write_advanced_godot_package(package, dest, authorized=True)

    def test_explicit_offline_cli_can_write_only_to_an_unused_destination(self):
        receipt = run_advanced_session("dialogue", actions=CONSENSUS)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "receipt.json"
            destination = Path(temp) / "native_dialogue"
            source.write_text(json.dumps(receipt), encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["godot-export", "--session", str(source),
                                      "--output", str(destination)]), 2)
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli([
                    "godot-export", "--session", str(source),
                    "--output", str(destination), "--trusted-local-operator"
                ]), 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary["native_editor"], "dialogue")
            self.assertTrue((destination / "godot/game.json").exists())


class NativeDialogueStudioTests(unittest.TestCase):
    def test_studio_custody_and_native_source_download(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = GameWorkspace.create(Path(temp) / "studio", authorized=True)
            ws.create_project("social_game", "hybrid", authorized=True)
            server = create_workspace_server(ws, port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def request(body, token=True):
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=8)
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["X-Game-Studio-Token"] = server.secret
                connection.request("POST", "/api/advanced-godot-package",
                                   json.dumps(body), headers)
                res = connection.getresponse()
                code, data = res.status, json.loads(res.read())
                connection.close()
                return code, data
            try:
                scene = make_advanced_scene("dialogue", seed=2)
                receipt = run_advanced_session("dialogue", actions=CONSENSUS,
                                               seed=2, scene=scene)
                status, body = request({"session": receipt})
                self.assertEqual(status, 200)
                self.assertEqual(body["engine"], "dialogue")
                self.assertFalse(body["gameplay_native_verified_by_this_request"])
                self.assertFalse(body["source_project_mutated"])
                archive = b64decode(body["zip_base64"], validate=True)
                self.assertEqual(sha256(archive).hexdigest(), body["zip_sha256"])
                with ZipFile(BytesIO(archive)) as zipfile:
                    self.assertIn(
                        "original-godot-dialogue/godot/scripts/main.gd",
                        zipfile.namelist())
                self.assertEqual(request({"session": receipt}, False)[0], 403)
                forged = deepcopy(receipt)
                forged["state"]["checkpoint"] = False
                self.assertEqual(request({"session": forged})[0], 400)
                page = render_workspace_html("x"*32).decode()
                self.assertIn('"factory","colony","economy","dialogue"', page)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
