"""User-visible endurance CLI runs actual journal read and vault reopen cycles."""
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_game_frontier_endurance import main
from tests.test_game_frontier_quest_ops_cli import NativeQuestOperationsCLITests


class GameFrontierEnduranceCLITests(NativeQuestOperationsCLITests):
    def test_evidence_finite_12_cycle_endurance_in_operator_cli(self):
        path=self.folder/"endurance.sqlite"
        args=[
            "--signed-gdd",str(self.folder/"gdd.json"),
            "--scene-json",str(self.folder/"scene.json"),
            "--journal",str(self.fixture.journal.path),
            "--event-pages-json",str(self.folder/"pages.json"),
            "--quest-graph-json",str(self.folder/"graph.json"),
            "--quest-approvals-json",str(self.folder/"approved.json"),
            "--actor-id","hero","--vault",str(path),
            "--cycles","12","--frames-per-window","2",
            "--retain-latest","2","--crash-interval","3",
            "--recovery-report-json",str(self.folder/"external-recovery.json"),
            "--max-cycle-ms","120000","--max-vault-bytes","33554432",
        ]
        stdout,stderr=StringIO(),StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            code=main(args)
        self.assertEqual(code,0,stderr.getvalue())
        result=json.loads(stdout.getvalue())
        self.assertEqual(result["cycles_executed"],12)
        self.assertEqual(result["source_frames_cold_replayed"],5)
        self.assertEqual(result["cycle_evidence"][-1]["replayed_through"],4)
        self.assertGreater(result["crash_rollbacks_executed"],0)
        self.assertEqual(len(result["receipt_digest"]),64)
        self.assertEqual(result["max_cycle_ms"],120000)
        self.assertGreater(result["peak_cycle_elapsed_ns"],0)
        self.assertTrue(path.is_file())
        manifest=json.loads((self.folder/"external-recovery.json").read_text())
        self.assertEqual(result["external_recovery_report_digest"],manifest["receipt_digest"])
        self.assertEqual(manifest["latest_verified_frame"],4)
        self.assertEqual(manifest["sqlite_health"]["sqlite_check"],"ok")
