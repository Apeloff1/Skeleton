"""Adversarial Jeeves whole-app coverage: files != executable capabilities."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
import json

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory,JeevesAppwideRuntime,JeevesAppwideError,
    MAX_PAGE,OPERATIONS,digest)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace


class AppwideCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)/"repository"
        root.mkdir()
        self.root=root
        directories={
            "skeleton/ai/game_builder":"scene_editor.py",
            "skeleton/ai/webcrawler":"dragon_crawler.py",
            "backend/core":"universal_forge.py",
            "apps/jeeves/src":"director.js",
            "frontend/editor":"drag_canvas.tsx",
            "docs/internal":"architecture.md",
            "satellites/branch-snapshots":"evidence.json",
        }
        for directory,name in directories.items():
            folder=root/directory
            folder.mkdir(parents=True)
            (folder/name).write_text("source test\n",encoding="utf8")
        (root/"skeleton/ai/game_builder/secret_token.key").write_text(
            "NO TOKEN EXPOSURE",encoding="utf8")
        (root/".env").write_text("PRIVATE_ENV_DATA",encoding="utf8")
        (root/".git").mkdir()
        (root/".git/config").write_text("CREDENTIALS")
        self.inv=AppwideInventory(root)
        self.report=self.inv.scan()
        self.run=JeevesAppwideRuntime(self.inv)

    def test_reports_every_regular_file_without_claiming_every_file_operates(self):
        self.assertEqual(self.report["scanned_regular_files"],9)
        self.assertEqual(self.report["classified_files"],9)
        self.assertEqual(self.report["restricted_files"],2)
        self.assertFalse(self.report["all_files_executable"])
        self.assertFalse(self.report["all_features_working"])
        self.assertEqual(self.report["skipped_paths"],1)
        self.assertIn("forge",self.report["domains"])
        self.assertIn("crawler",self.report["domains"])
        self.assertIn("companion",self.report["domains"])
        self.assertIn("editor",self.report["domains"])
        self.assertTrue(self.inv.search(domain="forge")["files"])
        result=self.inv.search(query="forge",limit=1)
        self.assertEqual(result["total_matches"],1)
        self.assertFalse(result["files"][0]["executable_adapter_bound"])
        self.assertEqual(self.run.catalog()["registered_action_count"],len(OPERATIONS))

    def test_scale_with_thousands_of_files_and_exact_deterministic_paging(self):
        base=self.root/"skeleton/ai/runtime/tree"
        base.mkdir(parents=True)
        for i in range(1500):
            (base/f"component_{i:05d}.py").write_text(f"# {i}\n",encoding="utf8")
        report=self.inv.scan()
        self.assertEqual(report["scanned_regular_files"],1509)
        all_files=[]
        offset=0
        while True:
            page=self.inv.search(domain="runtime",limit=MAX_PAGE,
                                 offset=offset,
                                 expected_snapshot=report["snapshot_digest"])
            all_files.extend(x["path"] for x in page["files"])
            if page["next_offset"] is None:
                break
            self.assertGreater(page["next_offset"],offset)
            offset=page["next_offset"]
        self.assertEqual(len(all_files),1500)
        self.assertEqual(len(set(all_files)),1500)
        self.assertEqual(all_files,sorted(all_files))
        self.assertEqual(report,self.inv.scan())
        with self.assertRaises(JeevesAppwideError):
            self.inv.search(expected_snapshot="a"*64)

    def test_no_secrets_or_symlinks_or_path_traversal(self):
        for path in (".env","skeleton/ai/game_builder/secret_token.key",
                     ".git/config","../outside","foo/../.env"):
            with self.subTest(path=path),self.assertRaises(JeevesAppwideError):
                self.inv.source(path)
        path="backend/core/universal_forge.py"
        self.assertEqual(self.inv.source(path)["content"],"source test\n")
        (self.root/path).unlink()
        try:
            (self.root/path).symlink_to(self.root/".env")
        except (OSError,NotImplementedError):
            # Windows runners may not enable unprivileged developer symlinks.
            (self.root/path).write_text("changed after scan\n",encoding="utf8")
            with self.assertRaises(JeevesAppwideError):
                self.inv.source(path)
        else:
            with self.assertRaises(JeevesAppwideError):
                self.inv.source(path)
            self.inv.scan()
            self.assertGreaterEqual(self.inv.report()["skipped_paths"],2)

    def test_actual_editor_forge_companion_and_crawler_are_bound_with_receipts(self):
        catalog=self.run.invoke("editor.catalog",{})
        self.assertGreaterEqual(len(catalog["result"]["editors"]),40)
        template=self.run.invoke("editor.template",{"editor":"rpg"})
        self.assertEqual(template["result"]["path"],"systems/rpg.json")
        self.assertTrue(template["result"]["requires_approval"])
        tools=self.run.invoke("forge.tools",{})
        self.assertGreaterEqual(len(tools["result"]["tools"]),10)
        self.assertFalse(tools["result"]["any_tool_executed"])
        dragon=self.run.invoke("companion.visual",{"event_kind":"burn_complete"})
        self.assertEqual(dragon["result"]["pose"],"proud")
        crawler=self.run.invoke("crawler.plan",{})
        self.assertEqual(crawler["result"]["targets"],[])
        self.assertFalse(crawler["result"]["crawl_started"])
        for receipt in (catalog,template,tools,dragon,crawler):
            self.assertEqual(receipt["digest"],digest(
                {key:value for key,value in receipt.items() if key!="digest"}))
        with self.assertRaises(JeevesAppwideError):
            self.run.invoke("forges.execute_python",{"command":"print('danger')"})
        with self.assertRaises(JeevesAppwideError):
            self.run.invoke("companion.visual",{"event_kind":"arbitrary"})

    def test_approved_source_proposal_requires_exact_digest_and_never_writes(self):
        path="backend/core/universal_forge.py"
        digest_old=self.inv.source(path)["sha256"]
        payload={"path":path,"expected_sha256":digest_old,
                 "replacement":"source improvement\n",
                 "reason":"Replace original source with targeted refactored implementation"}
        with self.assertRaises(PermissionError):
            self.run.invoke("source.propose",payload)
        proposal=self.run.invoke("source.propose",payload,authorized=True)
        self.assertIn("-source test",proposal["result"]["diff"])
        self.assertIn("+source improvement",proposal["result"]["diff"])
        self.assertFalse(proposal["result"]["source_mutated"])
        self.assertFalse(proposal["result"]["committed"])
        self.assertEqual((self.root/path).read_text(),"source test\n")
        altered=dict(payload,expected_sha256="f"*64)
        with self.assertRaises(JeevesAppwideError):
            self.run.invoke("source.propose",altered,authorized=True)

    def test_self_improvement_is_review_only_and_requires_source_evidence(self):
        source="backend/core/universal_forge.py"
        baseline={"path":source,"replacement":"better original code\n",
                  "reason":"Improve deterministic forge performance and code structure"}
        with self.assertRaises(PermissionError):
            self.run.invoke("learning.improvement_proposal",baseline)
        with self.assertRaises(JeevesAppwideError):
            self.run.invoke("learning.improvement_proposal",baseline,
                            authorized=True)
        evidence=[{"source_digest":"a"*64,"claim":"Independently observed runtime improvement."},
                  {"source_digest":"b"*64,"claim":"Repeatable independent benchmark comparison."}]
        result=self.run.invoke("learning.improvement_proposal",
                               {**baseline,"evidence":evidence},authorized=True)
        self.assertFalse(result["result"]["normal_weights_modified"])
        self.assertFalse(result["result"]["hyperweights_modified"])
        self.assertFalse(result["result"]["code_automatically_deployed"])
        self.assertTrue(result["result"]["requires_independent_benchmark_improvement"])
        self.assertFalse(result["result"]["evidence_claims_independently_verified"])

    def test_active_project_edit_still_uses_exact_human_approval_flow(self):
        work=GameWorkspace.create(str(Path(self.tmp.name)/"workspace"),authorized=True)
        work.create_project("fable","rpg",authorized=True)
        runtime=JeevesAppwideRuntime(self.inv,workspace=work)
        tree=runtime.invoke("studio.tree",{"project":"fable"})
        self.assertTrue(tree["result"])
        with self.assertRaises(PermissionError):
            runtime.invoke("studio.propose",{
                "project":"fable","path":"game/original_notes.md",
                "text":"# Original notes\n","expected_sha256":sha256(b"").hexdigest(),
                "reason":"Original game story and systems need review"})
        proposal=runtime.invoke("studio.propose",{
            "project":"fable","path":"game/original_notes.md",
            "text":"# Original notes\n","expected_sha256":sha256(b"").hexdigest(),
            "reason":"Original game story and systems need review"},authorized=True)
        self.assertTrue(proposal["result"]["human_commit_required"])
        with self.assertRaises(JeevesAppwideError):
            runtime.invoke("studio.tree",{"project":"another"})

if __name__=="__main__":
    unittest.main()
