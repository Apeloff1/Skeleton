"""Adversarial contracts for the typed system-editor studios and mechanics."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace, WorkspaceError
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.system_editors import (
    SystemEditorError, catalog, editor_path, editor_source, make_editor_document,
    preview_editor, validate_editor_document,
)


class SystemCatalogTests(unittest.TestCase):
    def test_every_family_has_distinct_typed_fields_and_stable_defaults(self):
        specs = catalog()
        self.assertGreaterEqual(len(specs), 40)
        self.assertEqual(len({s["id"] for s in specs}), len(specs))
        self.assertGreaterEqual(sum(len(s["fields"]) for s in specs), 200)
        self.assertIn("maze", {s["id"] for s in specs})
        self.assertIn("rpg", {s["id"] for s in specs})
        for spec in specs:
            with self.subTest(spec=spec["id"]):
                self.assertGreaterEqual(len(spec["fields"]), 4)
                self.assertEqual(len({f["key"] for f in spec["fields"]}),
                                 len(spec["fields"]))
                document = make_editor_document(spec["id"])
                self.assertEqual(document, validate_editor_document(document))
                self.assertEqual(document, json.loads(editor_source(spec["id"])))
                self.assertEqual(editor_path(spec["id"]), "systems/" + spec["id"] + ".json")
                self.assertEqual(make_editor_document(spec["id"], document["settings"]),
                                 document)
                self.assertEqual(len(document["digest"]), 64)

    def test_reject_undocumented_values_and_checksum_forgery(self):
        self.assertRaises(SystemEditorError, make_editor_document, "not-real")
        for name, settings in (
            ("platformer", {"gravity": True}),
            ("platformer", {"gravity": -3}),
            ("platformer", {"jump_impulse": 100000}),
            ("platformer", {"unapproved_script": "print(1)"}),
            ("platformer", {"double_jump": "yes"}),
            ("maze", {"topology": "arbitrary_native_executable"}),
            ("rpg", {"party_size": 0}),
            ("rhythm", {"perfect_window_ms": 100, "hit_window_ms": 25}),
            ("npc_society", {"population": 5, "active_npcs": 100}),
            ("tactics", {"board_width": 4, "board_height": 4, "attack_range": 12}),
        ):
            with self.subTest(name=name, settings=settings):
                with self.assertRaises(SystemEditorError):
                    make_editor_document(name, settings)
        document = make_editor_document("racing")
        document["digest"] = "0" * 64
        with self.assertRaises(SystemEditorError):
            validate_editor_document(document)
        document = make_editor_document("racing")
        document["shell_command"] = "unsafe"
        with self.assertRaises(SystemEditorError):
            validate_editor_document(document)

    def test_repeatable_real_prototypes_and_invalid_actions(self):
        for name in ("platformer", "racing", "tactics", "tower_defense", "shooter",
                     "survival", "rhythm", "deck_battler"):
            with self.subTest(name=name):
                first = preview_editor(name)
                self.assertTrue(first["simulation_executed"])
                self.assertEqual(first["status"], "deterministic_prototype")
                self.assertEqual(first, preview_editor(name))
                self.assertEqual(len(first["digest"]), 64)
                self.assertTrue(first["state"])
        self.assertGreater(preview_editor("platformer")["state"]["x"], 0)
        self.assertGreater(preview_editor("racing")["state"]["distance"], 0)
        self.assertGreater(preview_editor("tower_defense")["state"]["spawned"], 0)
        self.assertGreater(preview_editor("shooter")["state"]["defeated"], 0)
        self.assertGreater(preview_editor("rhythm")["state"]["score"], 0)
        self.assertFalse(preview_editor("maze")["simulation_executed"])
        for system, action in (
            ("platformer","execute"), ("racing","teleport"),
            ("tactics","spawn_enemy"), ("tower_defense","refund"),
            ("shooter","infinite_ammo"), ("survival","cheat"),
            ("rhythm",12.25), ("deck_battler","god_mode"),
        ):
            with self.subTest(system=system, action=action):
                with self.assertRaises(SystemEditorError):
                    preview_editor(system, actions=[action])
        with self.assertRaises(SystemEditorError):
            preview_editor("racing", actions=["accelerate"] * 129)


class StudioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = GameWorkspace.create(Path(self.temp.name) / "work",
                                              authorized=True)
        self.workspace.create_project("new_world", "hybrid", authorized=True)

    def test_commit_requires_real_review_and_preserves_immutable_archives(self):
        source = editor_source("platformer", {"gravity": 4})
        empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        with self.assertRaises(PermissionError):
            self.workspace.propose("new_world", "systems/platformer.json", source,
                                   expected_sha256=empty, reason="Real platformer designer change",
                                   authorized=False)
        approved = self.workspace.propose(
            "new_world", "systems/platformer.json", source, expected_sha256=empty,
            reason="Review configured original platformer physics",
            authorized=True)
        self.assertFalse((self.workspace.root / "current/new_world/systems/platformer.json").exists())
        with self.assertRaises(PermissionError):
            self.workspace.commit(approved["proposal_id"], human_approved=False,
                                  authorized=True)
        accepted = self.workspace.commit(approved["proposal_id"], human_approved=True,
                                         authorized=True)
        self.assertEqual(accepted["sha256"], approved["after"])
        self.assertEqual(json.loads(self.workspace.read(
            "current", "new_world", "systems/platformer.json")["content"]),
            make_editor_document("platformer", {"gravity": 4}))
        with self.assertRaises(WorkspaceError):
            self.workspace.propose("new_world", "systems/platformer.json", source,
                                   expected_sha256=empty, reason="Reject stale source hash",
                                   authorized=True)
        archived = self.workspace.archive("new_world", demo=True, authorized=True)
        self.assertEqual(json.loads(self.workspace.read(
            "demos", archived["ref"], "systems/platformer.json")["content"]),
            make_editor_document("platformer", {"gravity": 4}))

    def test_wrong_document_identity_rejected_even_at_source_proposal(self):
        empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        wrong = editor_source("racing")
        with self.assertRaises(WorkspaceError):
            self.workspace.propose("new_world", "systems/platformer.json", wrong,
                                   expected_sha256=empty,
                                   reason="Wrong system should never be approved",
                                   authorized=True)
        forged = json.loads(editor_source("racing"))
        forged["digest"] = "f" * 64
        with self.assertRaises(SystemEditorError):
            self.workspace.propose("new_world", "systems/racing.json",
                                   json.dumps(forged), expected_sha256=empty,
                                   reason="Malformed system should never be approved",
                                   authorized=True)

    def test_authenticated_read_catalog_and_preview_without_write(self):
        server = create_workspace_server(self.workspace, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method, path, payload=None, token=True, origin=None):
            conn = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
            headers={"Host":"127.0.0.1:" + str(server.server_port)}
            if token: headers["X-Game-Studio-Token"] = server.secret
            if payload is not None:
                headers["Content-Type"]="application/json"
                if origin: headers["Origin"]=origin
            conn.request(method,path,body=json.dumps(payload) if payload is not None else None,
                         headers=headers)
            response=conn.getresponse()
            data=response.read();status=response.status
            conn.close()
            return status,json.loads(data)
        status, data=request("GET","/api/editors")
        self.assertEqual(status,200)
        self.assertGreaterEqual(len(data["editors"]),40)
        self.assertEqual(request("GET","/api/editors",token=False)[0],403)
        status, data=request("POST","/api/editor-preview",
                            {"editor":"racing","settings":{"laps":2}})
        self.assertEqual(status,200)
        self.assertEqual(data["path"],"systems/racing.json")
        self.assertTrue(data["preview"]["simulation_executed"])
        self.assertFalse(data["write_authorized"])
        self.assertFalse((self.workspace.root/"current/new_world/systems").exists())
        self.assertEqual(request("POST","/api/editor-preview",
                                 {"editor":"racing","settings":{"laps":2}},
                                 origin="https://evil.example")[0],403)
        self.assertEqual(request("POST","/api/editor-preview",
                                 {"editor":"racing","settings":{"laps":0}})[0],400)

    def test_visual_editor_is_offline_and_uses_review_controls(self):
        html=render_workspace_html("Z"*32).decode()
        for token in ('id="system-kind"', 'id="system-fields"',
                      'id="system-stage"', 'id="system-try"',
                      "Review proposed edit","Content-Security-Policy"):
            self.assertIn(token,html)
        self.assertNotIn("https://",html)


if __name__=="__main__":
    unittest.main()
