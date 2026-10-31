"""CLI uses the original signed scene and capture journal, not HUD claims."""
from contextlib import redirect_stdout,redirect_stderr
from copy import deepcopy
from io import StringIO
import json
import unittest

from scripts.verify_game_frontier_instruments import main
from tests.test_game_frontier_quest_ops_cli import NativeQuestOperationsCLITests
from tests.test_game_frontier_native_instrument_trace import NativeInstrumentTraceTests


class NativeInstrumentVerifierCLITests(NativeQuestOperationsCLITests):
    def setUp(self):
        super().setUp()
        self.scene["advanced_physics"]={"airflow_velocity_xyz":[0.,0.,0.]}
        self.write("scene",self.scene)
        self.journal=self.fixture.journal
        self.telemetry=self.folder/"instrument_trace.jsonl"
        self.trace=NativeInstrumentTraceTests.source_trace(self)
        self.telemetry.write_text(
            "".join(json.dumps(x,sort_keys=True)+"\n" for x in self.trace))
        self.arguments=[
            "--signed-gdd",str(self.folder/"gdd.json"),
            "--scene-json",str(self.folder/"scene.json"),
            "--journal",str(self.journal.path),
            "--telemetry-jsonl",str(self.telemetry),
            "--actor-id","hero",
        ]

    def run_verify(self,*extra):
        stdout,stderr=StringIO(),StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            status=main([*self.arguments,*extra])
        return status,json.loads(stdout.getvalue()) if stdout.getvalue() else None,stderr.getvalue()

    def test_operator_verifies_all_replayed_game_ticks(self):
        status,report,error=self.run_verify()
        self.assertEqual(status,0,error)
        self.assertEqual(report["verified_physics_frames"],5)
        self.assertEqual(report["source_actor_digest"],"a"*64)
        self.assertEqual(len(report["receipt_digest"]),64)

    def test_actor_and_truncated_stream_fail_closed(self):
        status,_,error=self.run_verify("--actor-id","intruder")
        self.assertEqual(status,2)
        self.assertIn("must match",error)
        self.telemetry.write_text("".join(json.dumps(x)+"\n" for x in self.trace[:-1]))
        status,_,error=self.run_verify()
        self.assertEqual(status,2)
        self.assertIn("does not cover every canonical source tick",error)

    def test_manipulated_authoritative_scene_airflow_not_silent(self):
        wrong=deepcopy(self.scene)
        wrong["advanced_physics"]["airflow_velocity_xyz"]=[100,200,300]
        self.write("scene",wrong)
        status,_,error=self.run_verify()
        self.assertEqual(status,2)
        self.assertIn("wind",error)
