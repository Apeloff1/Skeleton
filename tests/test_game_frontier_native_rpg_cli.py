"""Operator native RPG event evaluator; source GDD and persisted physics required."""
from __future__ import annotations
import io
import json
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_game_frontier_capture import main
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from tests.test_game_frontier_native_chunks import sample
from tests.test_game_frontier_position_frames import gdd


class NativeRPGEvidenceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.anchor=bind_signed_gdd(gdd())
        self.gdd_json=self.folder/"gdd.json"
        self.scene_json=self.folder/"scene.json"
        self.db=self.folder/"journal.sqlite"
        self.pages_json=self.folder/"events.json"
        self.gdd_json.write_text(json.dumps(gdd()))
        self.scene_json.write_text(json.dumps({
            "schema":"skeleton.game.frontier_godot_overlay.v1",
            "origin_candidate_digest":"d"*64,
            "native_capture":{
                "enabled":True,"candidate_digest":"d"*64,
                "gdd_digest":self.anchor.source_digest,"fps":60,
                "actor_id":"hero","actor_asset_digest":"a"*64,
                "actors":[{"id":"hero","source_digest":"a"*64},
                          {"id":"npc","source_digest":"b"*64},
                          {"id":"island","source_digest":"c"*64}],
            },
        }))
        self.pages_json.write_text(json.dumps({
            "schema":"skeleton.game.native_rpg_pages.v1","pages":[{
                "id":"fall_warning","priority":20,
                "conditions":[{"signal":"fall_speed_mps",
                               "comparison":"at_least","threshold":10.}],
                "actions":[{"kind":"show_dialogue","channel":"ui",
                            "target":"hero","value":"falling"}],
                "required_flags":[],"cooldown_ms":0,"repeat":False,
                "enabled":True,
            }],
        }))
        with FrameReceiptJournal(self.db,self.anchor) as journal:
            ingestor=GodotPhysicsCaptureIngestor(
                journal,candidate_digest="d"*64,
                allowed_assets={"hero":"a"*64,"npc":"b"*64,"island":"c"*64})
            for i in range(3):
                ingestor.ingest(sample(i,self.anchor.source_digest))

    def argv(self,*extra):
        return [
            "evaluate-events","--signed-gdd",str(self.gdd_json),
            "--scene-json",str(self.scene_json),
            "--journal",str(self.db),
            "--event-pages-json",str(self.pages_json),
            "--actor-id","hero",*extra,
        ]

    def test_operator_event_page_capture_and_pagination(self):
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(self.argv("--start-frame","1","--event-limit","2")),0)
        data=json.loads(output.getvalue())
        evaluation=data["evaluation"]
        self.assertEqual(evaluation["source_prefix_verified_frames"],3)
        self.assertEqual(evaluation["start_frame"],1)
        self.assertEqual(len(evaluation["entries"]),2)
        self.assertEqual(evaluation["candidate_fire_count"],0)
        self.assertEqual(evaluation["last_fired_clocks_ms"]["fall_warning"],0)
        self.assertEqual(len(evaluation["receipt_digest"]),64)

    def test_invalid_authored_page_or_actor_refuses_execution(self):
        for bad in (
            self.argv("--actor-id","missing"),
            self.argv("--event-limit","0"),
        ):
            sink=io.StringIO()
            with redirect_stderr(sink):
                self.assertEqual(main(bad),2)
        self.pages_json.write_text(json.dumps({"schema":"invalid","pages":[]}))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(self.argv()),2)

    def test_source_verified_flags_configuration(self):
        self.pages_json.write_text(json.dumps({
            "schema":"skeleton.game.native_rpg_pages.v1","pages":[{
                "id":"conditional","priority":30,
                "conditions":[{"signal":"native_contact_count",
                               "comparison":"at_least","threshold":1.}],
                "actions":[{"kind":"show_dialogue","channel":"ui",
                            "target":"hero","value":"contact"}],
                "required_flags":[{"name":"quest_approved","value":True}],
                "cooldown_ms":0,"repeat":False,"enabled":True,
            }],
        }))
        f=self.folder/"flags.json"
        f.write_text(json.dumps({
            "schema":"skeleton.game.native_rpg_flags.v1",
            "flags":{"quest_approved":True},
        }))
        out=io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(self.argv("--event-flags-json",str(f))),0)
        self.assertEqual(json.loads(out.getvalue())[
            "evaluation"]["candidate_fire_count"],1)

    def test_actor_binding_and_scene_source_identity_cannot_be_swapped(self):
        original=json.loads(self.pages_json.read_text())
        mutated=dict(original,source_actor_id="villain")
        self.pages_json.write_text(json.dumps(mutated))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(self.argv()),2)
        self.pages_json.write_text(json.dumps(original))
        wrong_scene=json.loads(self.scene_json.read_text())
        wrong_scene["native_capture"]["candidate_digest"]="f"*64
        wrong_scene["origin_candidate_digest"]="f"*64
        self.scene_json.write_text(json.dumps(wrong_scene))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(self.argv()),2)
