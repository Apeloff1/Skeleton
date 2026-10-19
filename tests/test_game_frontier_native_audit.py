"""Verified, bounded, read-only native physics diagnostics and CLI wiring."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_frontier_native_audit import (
    analyze_native_capture,NativeAuditError,
)
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from tests.test_game_frontier_native_chunks import sample
from tests.test_game_frontier_position_frames import gdd


class NativeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db=Path(self.directory.name)/"diagnostics.sqlite"
        self.anchor=bind_signed_gdd(gdd())

    def populated(self, *, frames=5, dynamics=True):
        journal=FrameReceiptJournal(self.db,self.anchor)
        ingestor=GodotPhysicsCaptureIngestor(
            journal,candidate_digest="d"*64,
            allowed_assets={"hero":"a"*64,"npc":"b"*64,"island":"c"*64})
        for index in range(frames):
            doc=sample(index,self.anchor.source_digest)
            if dynamics:
                doc["native_dynamics_schema"]="skeleton.game.native_actor_dynamics.v1"
                for actor in doc["actors"]:
                    hero=actor["id"]=="hero"
                    actor["physics_body"]={
                        "mode":"rigid" if hero else "static",
                        "mass_kg":50. if hero else 0.,
                        "friction":.4,"restitution":.2,
                        "kinetic_energy_j":10900. if hero else 0.,
                        "contact_actor_ids":[],
                        "external_contact_count":actor["contact_count"],
                    }
            ingestor.ingest(doc)
        return journal

    def test_summary_actor_filter_distance_energy_and_replay(self):
        with self.populated() as journal:
            report=analyze_native_capture(journal,actor_id="hero")
            self.assertEqual(report["frames_scanned"],5)
            self.assertEqual(report["full_prefix_replay_verified"],5)
            self.assertEqual(len(report["actor_metrics"]),1)
            hero=report["actor_metrics"][0]
            self.assertEqual(hero["samples"],5)
            self.assertEqual(hero["id"],"hero")
            self.assertAlmostEqual(hero["path_distance_m"],.08,places=5)
            self.assertAlmostEqual(hero["net_displacement_m"],.08,places=5)
            self.assertEqual(hero["peak_reported_kinetic_energy_j"],10900.)
            self.assertEqual(hero["positive_contact_ticks"],5)
            self.assertEqual(hero["chunk_migrations"],1)
            self.assertEqual(report,analyze_native_capture(journal,actor_id="hero"))
            self.assertEqual(len(report["receipt_digest"]),64)

    def test_paginated_window_and_legacy_without_false_energy(self):
        with self.populated(frames=6,dynamics=False) as journal:
            report=analyze_native_capture(journal,start_frame=3,max_frames=2)
            self.assertEqual(report["full_prefix_replay_verified"],5)
            self.assertEqual(report["frames_scanned"],2)
            self.assertEqual(report["through_frame"],4)
            self.assertEqual(len(report["actor_metrics"]),3)
            self.assertTrue(all(row["peak_reported_kinetic_energy_j"] is None
                                for row in report["actor_metrics"]))

    def test_invalid_selection_and_budget_rejected(self):
        with self.populated() as journal:
            for kwargs in (
                {"start_frame":-1},{"start_frame":25},
                {"max_frames":0},{"max_frames":5000},
                {"actor_id":"missing"},{"actor_id":""},
                {"acceleration_threshold_mps2":float("nan")},
                {"energy_change_threshold_j":-5},
            ):
                with self.subTest(args=kwargs),self.assertRaises(NativeAuditError):
                    analyze_native_capture(journal,**kwargs)

    def test_replay_rejects_corrupt_cas_not_only_telemetry_payload(self):
        with self.populated() as journal:
            self.assertEqual(analyze_native_capture(journal)["frames_scanned"],5)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest IN "
                       "(SELECT evidence_digest FROM frontier_commits WHERE frame=2)")
        with FrameReceiptJournal(self.db,self.anchor) as journal:
            with self.assertRaises(ValueError):
                analyze_native_capture(journal)

    def test_fork_source_and_independent_digests(self):
        with self.populated() as journal:
            original=analyze_native_capture(journal,max_frames=3)
            journal.fork("checkpoint",through=2)
        with FrameReceiptJournal(self.db,self.anchor,track="checkpoint") as fork:
            report=analyze_native_capture(fork,max_frames=3)
            self.assertEqual(report["source_frame_evidence_chain"],
                             original["source_frame_evidence_chain"])
            self.assertNotEqual(report["receipt_digest"],original["receipt_digest"])


if __name__=="__main__":
    unittest.main()
