"""Godot 4 opt-in runtime physics capture and source-linked durable replay."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameObject, bind_signed_gdd,
)
from skeleton.jeeves.game_frontier_native_capture import (
    GodotPhysicsCaptureIngestor, NativeObservationError,
)
from skeleton.jeeves.game_frontier_receipt_journal import (
    FrameReceiptJournal, FrameJournalError,
)
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.forge.game_frontier_godot import (
    emit_frontier_godot_overlay, FrontierGodotError,
)
from tests.test_game_frontier_advanced_scene import scene_params
from tests.test_game_frontier_position_frames import gdd


SHA="a"*64
CANDIDATE="b"*64


def native(tick: int, *, fps: int = 60, x: float = 2.,
           actor: str = "hero", source: str = SHA,
           candidate: str = CANDIDATE, gdd_hash: str = "") -> dict:
    return {
        "schema": "skeleton.game.native_physics_observation.v1",
        "native_engine": "godot4_physics",
        "authority": "untrusted_native_candidate_observation_not_attested",
        "scene_candidate_digest": candidate,
        "signed_gdd_digest": gdd_hash,
        "native_tick": tick,
        "ticks_usec": 1_000_000 + tick*20_000,
        "fps": fps,
        "actors": [{
            "id":actor, "source_digest":source,
            "world_xyz_m":[x,0.,1.], "velocity_xyz_mps":[6.,0.,0.],
        }],
    }


class NativeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"observed.db"
        self.anchor=bind_signed_gdd(gdd())

    def pipeline(self, *, fps=60):
        journal=FrameReceiptJournal(self.db,self.anchor)
        ingestor=GodotPhysicsCaptureIngestor(
            journal,candidate_digest=CANDIDATE,
            allowed_assets={"hero":SHA})
        return journal,ingestor

    def test_opt_in_godot_recorder_preserves_existing_default(self):
        cfg=scene_params()
        cfg.update(frame_gdd=self.anchor,frame_index=0,
            frame_objects=(FrameObject("hero",Vec3(0,0,30),
                                      Vec3(0,0,-20),SHA),))
        scene=compile_frontier_scene(**cfg)
        default=emit_frontier_godot_overlay(scene)
        raw=json.loads(default["frontier/data/scene.json"])
        self.assertEqual(raw["native_capture"],{"enabled":False})
        generated=emit_frontier_godot_overlay(
            scene,enable_native_capture=True,native_capture_max_frames=200)
        payload=json.loads(generated["frontier/data/scene.json"])
        settings=payload["native_capture"]
        self.assertEqual(settings["candidate_digest"],scene.manifest_digest)
        self.assertEqual(settings["actor_id"],"hero")
        self.assertEqual(settings["actor_asset_digest"],SHA)
        self.assertEqual(settings["gdd_digest"],self.anchor.source_digest)
        self.assertEqual(settings["max_frames"],200)
        code=generated["frontier/frontier_scene.gd"]
        for snippet in ("_record_native_physics()",
                        'FileAccess.open("user://frontier_native_physics.jsonl"',
                        "Time.get_ticks_usec()",
                        "Engine.physics_ticks_per_second",
                        '"world_xyz_m": xyz',
                        "untrusted_native_candidate_observation_not_attested"):
            self.assertIn(snippet,code)
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(scene,enable_native_capture=True,
                                        native_capture_max_frames=0)

    def test_export_fails_closed_without_signed_frame_provenance(self):
        scene=compile_frontier_scene(**scene_params())
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(scene,enable_native_capture=True)

    def test_ingest_observed_native_samples_and_reopen_replay_every_fps(self):
        for fps in (30,50,60,120):
            self.db=Path(self.temp.name)/f"{fps}.sqlite"
            journal,ingestor=self.pipeline(fps=fps)
            with journal:
                zero=ingestor.ingest(native(0,fps=fps,x=2.,gdd_hash=self.anchor.source_digest))
                one=ingestor.ingest(native(1,fps=fps,x=2+.02,
                                          gdd_hash=self.anchor.source_digest))
                self.assertEqual(zero["frame"],0)
                self.assertEqual(one["frame"],1)
                self.assertEqual(journal.load(1)[0].frame_index,1)
                self.assertEqual(journal.native_sample(0)["native_tick"],0)
                self.assertEqual(journal.native_sample(1)["native_tick"],1)
                self.assertEqual(journal.replay()["verified_frames"],2)
                journal.fork("recovery",through=0)
                self.assertEqual(journal.stats()["deduplicated_blobs"],8)  # frame, chunk, native sample, native chunk proof
            with FrameReceiptJournal(self.db,self.anchor,track="recovery") as recovered:
                self.assertEqual(recovered.replay()["verified_frames"],1)
                self.assertEqual(recovered.native_sample(0)["scene_candidate_digest"],
                                 CANDIDATE)

    def test_jsonl_file_ingests_without_executing_payload(self):
        data=[native(i,x=2+i*.03,gdd_hash=self.anchor.source_digest)
              for i in range(5)]
        path=Path(self.temp.name)/"physics.jsonl"
        path.write_text("".join(json.dumps(v)+"\n" for v in data))
        journal,ingestor=self.pipeline()
        with journal:
            committed=ingestor.ingest_file(path)
            self.assertEqual(len(committed),5)
            self.assertEqual(journal.replay()["verified_frames"],5)

    def test_rejects_forged_actor_asset_scene_and_physics_clock(self):
        journal,ingestor=self.pipeline()
        with journal:
            for corrupt in (
                {"scene_candidate_digest":"d"*64},
                {"native_tick":1},
                {"native_engine":"unverified_fake"},
                {"fps":144},
                {"actors":[{"id":"hero","source_digest":"d"*64,
                            "world_xyz_m":[2.,0.,1.],
                            "velocity_xyz_mps":[6.,0.,0.]}]},
                {"actors":[]},
                {"ticks_usec":-10},
            ):
                payload=dict(native(0,gdd_hash=self.anchor.source_digest))
                payload.update(corrupt)
                with self.assertRaises(NativeObservationError):
                    ingestor.ingest(payload)
                self.assertEqual(journal.stats()["head"],-1)
            ingestor.ingest(native(0,gdd_hash=self.anchor.source_digest))
            stale=native(1,x=2.02,gdd_hash=self.anchor.source_digest)
            stale["ticks_usec"]=100
            with self.assertRaises(NativeObservationError):
                ingestor.ingest(stale)
            impossible=native(1,x=200,gdd_hash=self.anchor.source_digest)
            with self.assertRaises(NativeObservationError):
                ingestor.ingest(impossible)
            self.assertEqual(journal.replay()["verified_frames"],1)

    def test_corrupted_native_blob_refuses_replay(self):
        journal,ingestor=self.pipeline()
        with journal:
            frame=ingestor.ingest(native(0,gdd_hash=self.anchor.source_digest))
            native_sha=frame["native_capture_digest"]
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                       (native_sha,))
        with FrameReceiptJournal(self.db,self.anchor) as journal:
            with self.assertRaises(FrameJournalError):
                journal.native_sample(0)
            with self.assertRaises(FrameJournalError):
                journal.replay()

    def test_rejects_over_budget_and_malformed_jsonl(self):
        journal=FrameReceiptJournal(self.db,self.anchor)
        ingestor=GodotPhysicsCaptureIngestor(
            journal,candidate_digest=CANDIDATE,allowed_assets={"hero":SHA},
            max_samples=1)
        with journal:
            ingestor.ingest(native(0,gdd_hash=self.anchor.source_digest))
            with self.assertRaises(NativeObservationError):
                ingestor.ingest(native(1,x=2.02,gdd_hash=self.anchor.source_digest))
            with self.assertRaises(NativeObservationError):
                ingestor.ingest_jsonl(["not-json"])
            with self.assertRaises(NativeObservationError):
                ingestor.ingest_jsonl([" "*150000])


if __name__=="__main__":
    unittest.main()
