"""User-run signed GDD native Godot observation CLI end-to-end tests."""
from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_game_frontier_capture import main
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from tests.test_game_frontier_position_frames import gdd


class OperatorCLIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.bible=gdd()
        self.anchor=bind_signed_gdd(self.bible)
        self.gdd_file=self.directory/"signed_gdd.json"
        self.gdd_file.write_text(json.dumps(self.bible))
        self.digest="b"*64
        self.asset="a"*64
        self.scene=self.directory/"scene.json"
        self.overlay={
            "schema":"skeleton.game.frontier_godot_overlay.v1",
            "origin_candidate_digest":self.digest,
            "native_capture":{
                "enabled":True,"candidate_digest":self.digest,
                "gdd_digest":self.anchor.source_digest,
                "fps":60,"actor_id":"hero","actor_asset_digest":self.asset,
                "max_frames":32,
            },
        }
        self.scene.write_text(json.dumps(self.overlay))
        self.capture=self.directory/"source.jsonl"
        self.db=self.directory/"receipts.sqlite"

    def args(self,*extra):
        return [*extra,"--signed-gdd",str(self.gdd_file),
                "--scene-json",str(self.scene),
                "--journal",str(self.db)]

    def sample(self,n):
        return {
            "schema":"skeleton.game.native_physics_observation.v1",
            "native_engine":"godot4_physics",
            "authority":"untrusted_native_candidate_observation_not_attested",
            "scene_candidate_digest":self.digest,
            "signed_gdd_digest":self.anchor.source_digest,
            "native_tick":n,"ticks_usec":100000+n*20000,
            "fps":60,
            "actors":[{
                "id":"hero","source_digest":self.asset,
                "world_xyz_m":[2+n*.02,0,1],
                "velocity_xyz_mps":[6,0,0],
            }],
        }

    def run_command(self,operation,*extras):
        stdout=StringIO()
        stderr=StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            code=main(self.args(operation,*extras))
        return code,stdout.getvalue(),stderr.getvalue()

    def test_ingest_verify_fork_restore_cli(self):
        self.capture.write_text("".join(
            json.dumps(self.sample(n))+"\n" for n in range(4)))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["samples_committed"],4)
        code,out,err=self.run_command("verify")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["replay"]["verified_frames"],4)
        code,out,err=self.run_command("fork","--fork-track","safety_2",
                                      "--through","2")
        self.assertEqual(code,0,err)
        code,out,err=self.run_command("verify","--track","safety_2")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["replay"]["verified_frames"],3)

    def test_idempotent_cli_resume_and_modified_capture_rejection(self):
        records=[self.sample(i) for i in range(4)]
        self.capture.write_text("".join(json.dumps(p)+"\n" for p in records))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,0,err)
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture),
                                      "--resume")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["samples_committed"],0)
        self.assertEqual(json.loads(out)["samples_reused"],4)
        modified=[dict(p) for p in records]
        modified[2]=dict(modified[2],ticks_usec=4321)
        self.capture.write_text("".join(json.dumps(p)+"\n" for p in modified))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture),
                                      "--resume")
        self.assertEqual(code,2)
        self.assertIn("differs",err)
        code,out,err=self.run_command("verify")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["replay"]["verified_frames"],4)

    def test_cli_uses_signed_native_multi_actor_catalog(self):
        second="b"*64
        extended=dict(self.overlay)
        settings=dict(self.overlay["native_capture"])
        settings["actors"]=[
            {"id":"hero","source_digest":self.asset},
            {"id":"rock","source_digest":second},
        ]
        extended["native_capture"]=settings
        self.scene.write_text(json.dumps(extended))
        one=self.sample(0)
        one["actors"].append({
            "id":"rock","source_digest":second,
            "world_xyz_m":[-33,0,0],
            "velocity_xyz_mps":[0,0,0]})
        one["native_chunk_size_m"]=32.
        one["native_chunks"]=[
            {"chunk_xy":[-2,0],"actor_ids":["rock"]},
            {"chunk_xy":[0,0],"actor_ids":["hero"]},
        ]
        self.capture.write_text(json.dumps(one)+"\n")
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["samples_committed"],1)
        code,out,err=self.run_command("verify")
        self.assertEqual(code,0,err)

    def test_unsigned_or_mismatched_gdd_cannot_ingest(self):
        self.capture.write_text(json.dumps(self.sample(0))+"\n")
        source=dict(self.overlay)
        source["native_capture"]=dict(source["native_capture"],
                                      gdd_digest="f"*64)
        self.scene.write_text(json.dumps(source))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,2)
        self.assertIn("signed-GDD-linked",err)
        self.assertEqual(out,"")

    def test_rejects_unqualified_scene_and_unbounded_capture(self):
        self.capture.write_text(" ".join(["x"]*140000))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,2)
        self.assertIn("rejected",err)
        source=dict(self.overlay)
        source["native_capture"]=dict(source["native_capture"],enabled=False)
        self.scene.write_text(json.dumps(source))
        code,out,err=self.run_command("verify")
        self.assertEqual(code,2)

    def test_cli_timeline_query_returns_hash_bound_chunk_frames(self):
        self.capture.write_text("".join(
            json.dumps(self.sample(n))+"\n" for n in range(8)))
        code,out,err=self.run_command("ingest","--capture-jsonl",str(self.capture))
        self.assertEqual(code,0,err)
        code,out,err=self.run_command("timeline","--start-frame","2",
                                      "--page-limit","3","--actor-id","hero")
        self.assertEqual(code,0,err)
        result=json.loads(out)
        self.assertEqual(result["page"]["start_frame"],2)
        self.assertEqual([x["frame"] for x in result["page"]["entries"]],[2,3,4])
        self.assertEqual(result["page"]["next_frame"],5)
        self.assertEqual(len(result["page"]["receipt_digest"]),64)
        self.assertTrue(all(x["native_evidence_digest"] for x in
                            result["page"]["entries"]))
        code,out,err=self.run_command("timeline","--actor-id","missing")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["page"]["entries"],[])

    def test_timeline_requires_coherent_spatial_filter_and_page_limits(self):
        with self.assertRaises(SystemExit):
            self.run_command("timeline","--chunk-x","2")
        code,out,err=self.run_command("timeline","--page-limit","100000")
        self.assertEqual(code,2)
        self.assertIn("bounded",err)

    def test_missing_capture_argument_does_not_fake_evidence(self):
        with self.assertRaises(SystemExit):
            self.run_command("ingest")


if __name__=="__main__":
    unittest.main()
