"""Three-lane studio: genre autoload, targeted AI edits, source custody and UI."""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.game_project_workspace import (
    GameWorkspace,WorkspaceError,
)
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import (
    create_workspace_server,StudioServerError,
)
from skeleton.ai.game_builder.game_workspace_cli import main as workspace_cli
from skeleton.ai.game_builder.quest_scene_forge import forge_director


class OriginalGameWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"original_studio"
        self.studio=GameWorkspace.create(self.root,authorized=True)
        self.world=forge_director(
            "original_workbench_world",seed=9311,
            regions=tuple(f"room_{i:02d}" for i in range(8)),
            quest_types=("main_story","regional_story"),stages=2,
        )
        self.studio.create_project(
            "first_game","rpg",authorized=True,
            director_json=self.world.payload(),
        )

    def test_three_sandboxed_trees_targeted_file_edit_and_archive(self):
        model=self.studio.tree()
        self.assertEqual(model["active"],"first_game")
        self.assertEqual(len(model["current"]),1)
        self.assertEqual(model["previous"],[])
        self.assertEqual(model["demos"],[])
        file=self.studio.read("current","first_game","game/director.json")
        self.assertTrue(file["version"]["editable"])
        before=file["version"]["sha256"]
        doc=json.loads(file["content"])
        doc["scenes"][0]["lighting"]="designer's original sea-green torchlight"
        replacement=json.dumps(doc,ensure_ascii=False,sort_keys=True)
        proposal=self.studio.propose(
            "first_game","game/director.json",replacement,
            expected_sha256=before,reason="Reframe scene 0 lighting to match user vision",
            authorized=True,
        )
        self.assertTrue(proposal["human_commit_required"])
        self.assertEqual(self.studio.read("current","first_game",
                                         "game/director.json")["version"]["sha256"],before)
        with self.assertRaises(PermissionError):
            self.studio.commit(proposal["proposal_id"],
                               human_approved=False,authorized=True)
        receipt=self.studio.commit(proposal["proposal_id"],
                                   human_approved=True,authorized=True)
        self.assertEqual(receipt["sha256"],hashlib.sha256(
            replacement.encode()).hexdigest())
        with self.assertRaises(WorkspaceError):
            self.studio.commit(proposal["proposal_id"],
                               human_approved=True,authorized=True)
        archival=self.studio.archive("first_game",authorized=True)
        snapshot=self.studio.read("previous",archival["ref"],"game/director.json")
        self.assertFalse(snapshot["version"]["editable"])
        self.assertIn("sea-green torchlight",snapshot["content"])
        demo=self.studio.archive("first_game",demo=True,authorized=True)
        self.assertEqual(demo["tree"],"demos")
        self.assertFalse(self.studio.read("demos",demo["ref"],
                           "project.json")["version"]["editable"])
        self.assertEqual(len(self.studio.projects("previous")),1)
        self.assertEqual(len(self.studio.projects("demos")),1)

    def test_genre_autoload_previous_to_new_current_without_mutating_archive(self):
        snapshot=self.studio.archive("first_game",authorized=True)
        result=self.studio.autoload_previous("rpg","second_original_game",
                                             authorized=True)
        self.assertEqual(result["active"],"second_original_game")
        source=self.studio.read("previous",snapshot["ref"],"game/director.json")
        clone=self.studio.read("current","second_original_game","game/director.json")
        self.assertEqual(source["content"],clone["content"])
        self.assertTrue(clone["version"]["editable"])
        copied_meta=json.loads(self.studio.read(
            "current","second_original_game","project.json")["content"])
        self.assertEqual(copied_meta["project"],"second_original_game")
        self.assertEqual(self.studio.tree()["active"],"second_original_game")
        with self.assertRaises(WorkspaceError):
            self.studio.autoload_previous("rpg","second_original_game",
                                          authorized=True)

    def test_demo_forks_to_full_editable_new_game_without_changing_immutable_demo(self):
        demo=self.studio.archive("first_game",demo=True,authorized=True)
        original=self.studio.read("demos",demo["ref"],"game/director.json")
        result=self.studio.fork_demo(demo["ref"],"remastered_demo",authorized=True)
        self.assertEqual(result["source_lane"],"demos")
        self.assertEqual(self.studio.active(),"remastered_demo")
        writable=self.studio.read("current","remastered_demo","game/director.json")
        self.assertTrue(writable["version"]["editable"])
        self.assertEqual(original["content"],writable["content"])
        data=json.loads(writable["content"])
        data["scenes"][0]["title"]="Original enhanced console edition"
        proposal=self.studio.propose(
            "remastered_demo","game/director.json",json.dumps(data),
            expected_sha256=writable["version"]["sha256"],
            reason="Use new original scene for evolved demo with author supervision.",
            authorized=True)
        self.studio.commit(proposal["proposal_id"],human_approved=True,authorized=True)
        still=self.studio.read("demos",demo["ref"],"game/director.json")
        self.assertEqual(still["content"],original["content"])
        self.assertNotEqual(self.studio.read(
            "current","remastered_demo","game/director.json")["content"],
            still["content"])
        with self.assertRaises(WorkspaceError):
            self.studio.fork_demo(demo["ref"],"remastered_demo",authorized=True)

    def test_proposal_path_traversal_binary_source_and_stale_file_rejected(self):
        file=self.studio.read("current","first_game","project.json")
        hash=file["version"]["sha256"]
        for bad in ("../another","/etc/passwd","game/../../bad.py",
                    "scripts/.hidden.js","asset.exe","game\u005cwrong.json"):
            with self.subTest(path=bad):
                with self.assertRaises(WorkspaceError):
                    self.studio.propose(
                        "first_game",bad,"{}",
                        expected_sha256=hash,
                        reason="Explicit human request to test invalid input",
                        authorized=True,
                    )
        with self.assertRaises(WorkspaceError):
            self.studio.propose("first_game","project.json","{}",
                                expected_sha256="0"*64,
                                reason="Test a stale base revision",authorized=True)
        with self.assertRaises(WorkspaceError):
            self.studio.propose(
                "first_game","project.json",'{"x":1,"x":2}',
                expected_sha256=hash,reason="Reject ambiguous JSON object",
                authorized=True,
            )
        with self.assertRaises(PermissionError):
            self.studio.propose(
                "first_game","project.json","{}",
                expected_sha256=hash,
                reason="Unauthorized generated patch",authorized=False,
            )
        with self.assertRaises(WorkspaceError):
            self.studio.propose(
                "first_game","project.json","{}",
                expected_sha256=hash,
                reason="x",authorized=True,
            )

    def test_cli_user_and_ai_authored_source_patch_requires_human_approval(self):
        # A new exact location uses the SHA-256 of empty source, and cannot
        # be created until a proposal is reviewed and explicitly committed.
        expected_empty=hashlib.sha256(b"").hexdigest()
        replacement=Path(self.temp.name)/"ai_proposed.md"
        replacement.write_text(
            "# Original narrative notes\nScene variations by player outcome.\n")
        from contextlib import redirect_stdout
        import io
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(workspace_cli([
                "propose","--root",str(self.root),
                "--project","first_game","--path","notes/design.md",
                "--file",str(replacement),
                "--expected-sha256",expected_empty,
                "--reason","Jeeves generated a targeted original narrative note",
                "--author","jeeves","--trusted-local-operator",
            ]),0)
        proposed=json.loads(output.getvalue())
        self.assertEqual(proposed["proposed_by"],"jeeves")
        self.assertFalse((self.root/"current/first_game/notes/design.md").exists())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(workspace_cli([
                "commit","--root",str(self.root),
                "--proposal-id",proposed["proposal_id"],
                "--human-reviewed","--trusted-local-operator",
            ]),0)
        self.assertIn("Scene variations",self.studio.read(
            "current","first_game","notes/design.md")["content"])

    def test_workbench_ui_javascript_is_syntactically_valid_and_offline(self):
        import shutil
        import subprocess
        import re
        from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
        html=render_workspace_html("a"*32).decode()
        js=re.findall(r"<script>(.*?)</script>",html,re.DOTALL)
        self.assertEqual(len(js),1)
        self.assertIn("game studio",html.lower())
        self.assertIn("Fork demo into current",html)
        self.assertIn("Plan affected modules",html)
        self.assertIn("Content-Security-Policy",html)
        self.assertNotIn("https://",html)
        if shutil.which("node"):
            script=Path(self.temp.name)/"workspace-ui.js"
            script.write_text(js[0],encoding="utf-8")
            checked=subprocess.run(["node","--check",str(script)],
                                   capture_output=True,text=True,timeout=10)
            self.assertEqual(checked.returncode,0,checked.stderr)

    def test_actual_local_browser_interface_and_authenticated_api(self):
        server=create_workspace_server(self.studio,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection=http.client.HTTPConnection("127.0.0.1",
                                               server.server_port,timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET","/")
        result=connection.getresponse()
        page=result.read().decode()
        self.assertEqual(result.status,200)
        self.assertIn('id="editor"',page)
        self.assertIn('id="tree"',page)
        self.assertIn("Content-Security-Policy",page)
        self.assertIn("Review proposed edit",page)
        self.assertIn("Autoload previous genre",page)
        self.assertNotIn("https://",page)
        connection.request("GET","/api/tree",
                           headers={"X-Game-Studio-Token":server.secret})
        result=connection.getresponse()
        self.assertEqual(result.status,200)
        self.assertEqual(json.loads(result.read())["active"],"first_game")
        connection.request("GET","/api/tree")
        denied=connection.getresponse();denied.read()
        self.assertEqual(denied.status,403)
        data=json.dumps({"project":"new_game","genre":"puzzle"})
        connection.request("POST","/api/create",body=data,headers={
            "Content-Type":"application/json",
            "X-Game-Studio-Token":server.secret,
            "Origin":"https://attacker.example",
        })
        denied=connection.getresponse();denied.read()
        self.assertEqual(denied.status,403)
        self.assertFalse((self.root/"current/new_game").exists())
        connection.request("POST","/api/create",body=data,headers={
            "Content-Type":"application/json",
            "X-Game-Studio-Token":server.secret,
            "Origin":f"http://127.0.0.1:{server.server_port}",
        })
        accepted=connection.getresponse();accepted.read()
        self.assertEqual(accepted.status,200)
        self.assertTrue((self.root/"current/new_game").exists())
        with self.assertRaises(StudioServerError):
            create_workspace_server(self.studio,host="0.0.0.0")

if __name__=="__main__":
    unittest.main()
