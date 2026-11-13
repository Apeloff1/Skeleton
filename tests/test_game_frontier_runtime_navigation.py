"""Native-recorded avatar -> fictional GPS -> GDD frame and survey evidence."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from skeleton.jeeves.game_frontier_runtime_navigation import (
    inspect_runtime_virtual_gps,RuntimeGameNavigationError,
)
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from tests.test_game_frontier_virtual_navigation import request
from tests.test_game_frontier_position_frames import gdd
from skeleton.jeeves.game_frontier_production import Vec3


class RuntimeNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"virtual_runtime.sqlite"
        self.gdd=bind_signed_gdd(gdd())
        self.source_id="b"*64
        self.actor_source="a"*64

    def native(self,n,fps=60):
        x=25.+.02*n
        return {
            "schema":"skeleton.game.native_physics_observation.v1",
            "native_engine":"godot4_physics",
            "authority":"untrusted_native_candidate_observation_not_attested",
            "scene_candidate_digest":self.source_id,
            "signed_gdd_digest":self.gdd.source_digest,
            "native_tick":n,"ticks_usec":200000+n*20000,
            "fps":fps,
            "actors":[{
                "id":"hero","source_digest":self.actor_source,
                "world_xyz_m":[x,25.,5.],
                "velocity_xyz_mps":[6.,0.,0.],
                "contact_count":0,
                "source_kind":"native_rigid_reference",
            }],
            "native_chunk_size_m":32.,
            "native_chunks":[{"chunk_xy":[0,0],"actor_ids":["hero"]}],
        }

    def prepare(self,fps=60):
        journal=FrameReceiptJournal(self.db,self.gdd)
        worker=GodotPhysicsCaptureIngestor(
            journal,candidate_digest=self.source_id,
            allowed_assets={"hero":self.actor_source})
        for i in range(3):
            worker.ingest(self.native(i,fps=fps))
        return journal

    def test_four_fps_runtime_fictional_beacon_and_survey_provenance(self):
        for fps in (30,50,60,120):
            self.db=Path(self.temp.name)/f"run{fps}.sqlite"
            with self.prepare(fps=fps) as journal:
                proof=inspect_runtime_virtual_gps(
                    journal,request(Vec3(25.04,25.,5.)),frame_index=2)
                self.assertFalse(proof["device_location_used"])
                self.assertEqual(proof["verified_replay_frames"],3)
                self.assertEqual(proof["world_id"],"frontier")
                self.assertEqual(proof["simulated_position"]["map_tile_xy"],[2,2])
                self.assertEqual(proof["simulated_position"]["survey"]["consistent"],True)
                self.assertEqual(proof["native_chunk_evidence_digest"],
                    journal.native_chunk_evidence(2)["receipt_digest"])
                self.assertEqual(proof["verified_frame_digest"],
                    journal.load(2)[0].receipt_digest)
                self.assertEqual(len(proof["receipt_digest"]),64)
                self.assertEqual(proof,inspect_runtime_virtual_gps(
                    journal,request(Vec3(25.04,25.,5.)),frame_index=2))

    def test_runtime_bridge_requires_actual_native_source_not_dummy_frame(self):
        from skeleton.jeeves.game_frontier_frame_coherence import (
            FrameObject,
        )
        with FrameReceiptJournal(self.db,self.gdd) as journal:
            journal.advance((FrameObject("hero",Vec3(25,25,5),
                            Vec3(6,0,0),"a"*64),),fps=60)
            with self.assertRaises(RuntimeGameNavigationError):
                inspect_runtime_virtual_gps(journal,request(),frame_index=0)

    def test_unapproved_or_missing_actor_refuses_world_fix(self):
        with self.prepare() as journal:
            with self.assertRaises(RuntimeGameNavigationError):
                inspect_runtime_virtual_gps(journal,request(),frame_index=99)
            from dataclasses import replace
            with self.assertRaises(RuntimeGameNavigationError):
                inspect_runtime_virtual_gps(journal,
                    replace(request(),actor_id="phantom"),frame_index=2)

    def test_corrupt_native_chunks_cannot_support_positioning(self):
        with self.prepare() as journal:
            digest=journal.native_chunk_evidence(2)["receipt_digest"]
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                       (digest,))
        with FrameReceiptJournal(self.db,self.gdd) as journal:
            with self.assertRaises(RuntimeGameNavigationError):
                inspect_runtime_virtual_gps(journal,request(),frame_index=2)


if __name__=="__main__":
    unittest.main()
