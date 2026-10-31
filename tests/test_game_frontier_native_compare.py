"""Cross-FPS and checkpoint native source comparison receipts."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from skeleton.jeeves.game_frontier_native_compare import (
    compare_native_sessions,NativeComparisonError,
)
from tests.test_game_frontier_native_capture import native
from tests.test_game_frontier_position_frames import gdd


class NativeSessionComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.anchor=bind_signed_gdd(gdd())

    def journal(self, name, fps, *, src="a"*64, spread=1.):
        session=FrameReceiptJournal(self.root/f"{name}.sqlite",self.anchor,track=name)
        ingestor=GodotPhysicsCaptureIngestor(
            session,candidate_digest="b"*64,allowed_assets={"hero":src})
        for tick in range(7 if fps==60 else 4):
            position=2.+spread*.02*tick*30/fps
            ingestor.ingest(native(tick,fps=fps,x=position,
                                   gdd_hash=self.anchor.source_digest,source=src))
        return session

    def test_30_and_60_hz_exact_rational_time_alignment(self):
        with self.journal("lower",30) as slow,self.journal("faster",60) as fast:
            report=compare_native_sessions(slow,fast,tolerance_m=.01)
            self.assertEqual(report["aligned_pairs_compared"],4)
            self.assertEqual([x["right_tick"] for x in report["shared_fixed_ticks"]],
                             [0,2,4,6])
            self.assertTrue(report["all_actor_positions_within_tolerance"])
            self.assertEqual(report["actor_metrics"][0]["matched_ticks"],4)
            self.assertIsNone(report["actor_metrics"][0][
                "maximum_reported_gameplay_force_delta_n"])
            self.assertAlmostEqual(report["actor_metrics"][0]["rms_position_delta_m"],0)
            self.assertEqual(report,compare_native_sessions(slow,fast,tolerance_m=.01))
            self.assertEqual(len(report["receipt_digest"]),64)

    def test_drift_metrics_flag_true_source_differences(self):
        with self.journal("lower",30) as slow,self.journal(
            "faster",60,spread=2.) as fast:
            result=compare_native_sessions(slow,fast,tolerance_m=.005)
            self.assertFalse(result["all_actor_positions_within_tolerance"])
            self.assertGreater(result["actor_metrics"][0][
                "position_drift_tolerance_exceedances"],0)
            self.assertGreater(result["actor_metrics"][0][
                "rms_position_delta_m"],0)

    def test_catalog_mismatch_actor_filter_and_bounds_rejected(self):
        with self.journal("lower",30) as slow,self.journal(
            "faster",60,src="c"*64) as fast:
            with self.assertRaises(NativeComparisonError):
                compare_native_sessions(slow,fast)
        with self.journal("a",30) as slow,self.journal("b",60) as fast:
            for kwargs in ({"actor_id":"unknown"},{"max_aligned_frames":1},
                           {"tolerance_m":float("nan")},{"tolerance_m":-1.}):
                with self.subTest(args=kwargs),self.assertRaises(NativeComparisonError):
                    compare_native_sessions(slow,fast,**kwargs)
            with self.assertRaises(NativeComparisonError):
                compare_native_sessions(slow,slow)

    def test_source_evidence_tamper_aborts_comparison(self):
        with self.journal("lower",30) as slow,self.journal("faster",60) as fast:
            self.assertEqual(compare_native_sessions(slow,fast)["aligned_pairs_compared"],4)
        damaged=self.root/"faster.sqlite"
        with sqlite3.connect(damaged) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest IN "
                       "(SELECT evidence_digest FROM frontier_commits WHERE frame=2)")
        with FrameReceiptJournal(self.root/"lower.sqlite",self.anchor,
                                 track="lower") as slow,FrameReceiptJournal(
                                 damaged,self.anchor,track="faster") as fast:
            with self.assertRaises(ValueError):
                compare_native_sessions(slow,fast)
