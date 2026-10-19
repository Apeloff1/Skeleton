"""Real operator CLI for batch persistence, independent auditing and comparison."""
from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_game_frontier_quest_tools import main
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests


class NativeQuestOperationsCLITests(unittest.TestCase):
    def setUp(self):
        fixture=NativeQuestBatchTests("test_all_window_sizes_preserve_quest_and_gdd_history")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.scene={
            "schema":"skeleton.game.frontier_godot_overlay.v1",
            "origin_candidate_digest":"d"*64,
            "native_capture":{
                "enabled":True,"candidate_digest":"d"*64,
                "gdd_digest":fixture.journal.gdd.source_digest,
                "actor_id":"hero","actor_asset_digest":"a"*64,
                "fps":60,"actors":[
                    {"id":"hero","source_digest":"a"*64},
                    {"id":"npc","source_digest":"b"*64},
                    {"id":"island","source_digest":"c"*64},
                ],
            },
        }
        from tests.test_game_frontier_position_frames import gdd
        self.write("gdd",gdd())
        self.write("scene",self.scene)
        self.write("pages",{
            "schema":"skeleton.game.native_rpg_pages.v1",
            "pages":[{
                "id":p.page_id,"priority":p.priority,
                "conditions":[c.__dict__ for c in p.conditions],
                "actions":[a.__dict__ for a in p.actions],
                "required_flags":[{"name":k,"value":v} for k,v in p.required_flags],
                "cooldown_ms":p.cooldown_ms,"repeat":p.repeat,"enabled":p.enabled,
            } for p in fixture.pages],
        })
        self.write("graph",fixture.graph)
        self.write("approved",fixture.approved)
        self.write("rejected",fixture.fixture.approval(authorized=()))
        self.base=[
            "--signed-gdd",str(self.folder/"gdd.json"),
            "--scene-json",str(self.folder/"scene.json"),
            "--journal",str(fixture.journal.path),
            "--actor-id","hero",
            "--event-pages-json",str(self.folder/"pages.json"),
            "--quest-graph-json",str(self.folder/"graph.json"),
            "--quest-approvals-json",str(self.folder/"approved.json"),
        ]

    def write(self,name,content):
        dest=self.folder/(name+".json")
        dest.write_text(json.dumps(content))
        return dest

    def run_cli(self,operation,*more):
        stdout,stderr=StringIO(),StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            code=main([operation,*self.base,*more])
        return code,json.loads(stdout.getvalue()) if stdout.getvalue() else None,stderr.getvalue()

    def test_operator_batch_audit_inspect_and_branch_compare(self):
        output=self.folder/"checkpoint.json"
        code,first,err=self.run_cli("batch","--frames-per-window","2",
                                    "--checkpoint-output-json",str(output))
        self.assertEqual(code,0,err)
        self.assertEqual(first["gameplay"]["verified_frame_count"],5)
        self.assertEqual(first["gameplay"]["window_count"],3)
        self.assertEqual(json.loads(output.read_text()),
                         first["gameplay"]["head_checkpoint"])
        code,proof,err=self.run_cli("audit","--checkpoint-input-json",str(output))
        self.assertEqual(code,0,err)
        self.assertEqual(proof["checkpoint_audit"]["verified_source_prefix_frames"],5)
        code,display,err=self.run_cli("inspect","--checkpoint-input-json",str(output))
        self.assertEqual(code,0,err)
        self.assertEqual(display["quest_journal"]["quests_completed"],1)
        self.assertEqual(display["quest_journal"]["quest_entries"][0]["stage_id"],"ending")

        other_checkpoint=self.write("other",self.fixture.replay(
            through_frame=4,frames_per_window=2)["head_checkpoint"])
        # Same approval manifest: comparator must report no divergence.
        code,comparison,err=self.run_cli(
            "compare","--checkpoint-input-json",str(output),
            "--other-approvals-json",str(self.folder/"approved.json"),
            "--other-checkpoint-json",str(other_checkpoint))
        self.assertEqual(code,0,err)
        self.assertTrue(comparison["outcome_difference"]["identical_quest_state"])

    def test_resume_requires_independent_root_and_refuses_overwrite(self):
        start=self.folder/"start.json"
        code,first,err=self.run_cli(
            "batch","--through","1","--frames-per-window","1",
            "--checkpoint-output-json",str(start))
        self.assertEqual(code,0,err)
        root=first["gameplay"]["head_checkpoint"]["receipt_digest"]
        end=self.folder/"end.json"
        code,following,err=self.run_cli(
            "batch","--through","4","--frames-per-window","2",
            "--checkpoint-input-json",str(start),
            "--expected-checkpoint-digest",root,
            "--checkpoint-output-json",str(end))
        self.assertEqual(code,0,err)
        self.assertEqual(following["gameplay"]["verified_frame_count"],3)
        self.assertEqual(following["gameplay"]["total_approved_events"],3)
        code,_,err=self.run_cli(
            "batch","--checkpoint-output-json",str(start))
        self.assertEqual(code,2)
        self.assertIn("destination must be a new regular file",err)
        with self.assertRaises(SystemExit):
            self.run_cli("batch","--checkpoint-input-json",str(start))

    def test_forged_stored_progress_denied_before_inspection(self):
        checkpoint=self.fixture.replay()["head_checkpoint"]
        checkpoint["flags"]["forged"]=True
        path=self.write("forged",checkpoint)
        code,_,err=self.run_cli("inspect","--checkpoint-input-json",str(path))
        self.assertEqual(code,2)
        self.assertIn("checkpoint differs",err)
