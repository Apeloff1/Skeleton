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

    def test_missing_capture_argument_does_not_fake_evidence(self):
        with self.assertRaises(SystemExit):
            self.run_command("ingest")


if __name__=="__main__":
    unittest.main()
