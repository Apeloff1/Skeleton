"""Native multi-actor runtime chunk proof, migration, rollback, recovery tests.

The Godot script tests validate generated source and protocol only; a real
Godot import/play on installed engine remains a separate acceptance gate.
"""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_native_chunks import (
    inspect_native_chunks, NativeChunkError,
)
from skeleton.jeeves.game_frontier_native_capture import (
    GodotPhysicsCaptureIngestor, NativeObservationError,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    bind_signed_gdd, FrameObject,
)
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_receipt_journal import (
    FrameReceiptJournal,FrameJournalError,
)
from skeleton.jeeves.game_frontier import compile_frontier_scene
from skeleton.forge.game_frontier_godot import (
    emit_frontier_godot_overlay, FrontierGodotError,
)
from tests.test_game_frontier_advanced_scene import scene_params
from tests.test_game_frontier_position_frames import gdd


A="a"*64
B="b"*64
C="c"*64
CANDIDATE="d"*64


def actors_at(tick: int):
    return [
        {"id":"hero", "source_digest":A,
         "source_kind":"native_rigid_reference","contact_count":1,
         "world_xyz_m":[31.99 + tick*.02, -1., 30.],
         "velocity_xyz_mps":[6., 0., -20.]},
        {"id":"npc", "source_digest":B,
         "source_kind":"generated_source_proxy","contact_count":0,
         "world_xyz_m":[-1., 0., 2.],
         "velocity_xyz_mps":[0., 0., 0.]},
        {"id":"island", "source_digest":C,
         "source_kind":"generated_source_proxy","contact_count":0,
         "world_xyz_m":[70., 0., 0.],
         "velocity_xyz_mps":[0., 0., 0.]},
    ]


def sample(tick:int, gdd_digest:str, *, fps:int=60, corrupted=False):
    all_actors=actors_at(tick)
    cells={}
    for item in all_actors:
        x,y,_=item["world_xyz_m"]
        import math
        key=(math.floor(x/32),math.floor(y/32))
        cells.setdefault(key,[]).append(item["id"])
    partition=[{"chunk_xy":list(k),"actor_ids":sorted(v)}
               for k,v in sorted(cells.items())]
    if corrupted:
        partition[0]["actor_ids"]=["bogus"]
    return {
        "schema":"skeleton.game.native_physics_observation.v1",
        "native_engine":"godot4_physics",
        "authority":"untrusted_native_candidate_observation_not_attested",
        "scene_candidate_digest":CANDIDATE,
        "signed_gdd_digest":gdd_digest,
        "native_tick":tick,"ticks_usec":100000+tick*20000,
        "fps":fps,"actors":all_actors,
        "native_chunk_size_m":32.,
        "native_chunks":partition,
    }


class NativeChunkMathTests(unittest.TestCase):
    def test_negative_coordinates_and_three_cell_exact_partition(self):
        report=inspect_native_chunks(sample(0,"e"*64))
        self.assertEqual(report["actor_count"],3)
        self.assertEqual(report["chunk_count"],3)
        self.assertTrue(report["native_partition_confirmed"])
        self.assertIn({"chunk_xy":[-1,0],"actor_ids":["npc"]},report["chunks"])
        self.assertIn({"chunk_xy":[0,-1],"actor_ids":["hero"]},report["chunks"])
        self.assertEqual(len(report["receipt_digest"]),64)
        self.assertEqual(report,inspect_native_chunks(sample(0,"e"*64)))

    def test_actor_collision_and_chunk_tampering_refused(self):
        for bad in (
            {"actors":[*actors_at(0),actors_at(0)[0]]},
            {"native_chunk_size_m":8.},
            {"native_chunks":[]},
            {"actors":[dict(actors_at(0)[0],contact_count=-1),*actors_at(0)[1:]]},
        ):
            source=sample(0,"f"*64)
            source.update(bad)
            with self.assertRaises(NativeChunkError):
                inspect_native_chunks(source)
        with self.assertRaises(NativeChunkError):
            inspect_native_chunks(sample(0,"f"*64,corrupted=True))

    def test_legacy_source_allowed_but_not_falsely_called_native_partition(self):
        source=sample(0,"0"*64)
        source.pop("native_chunks")
        source.pop("native_chunk_size_m")
        report=inspect_native_chunks(source)
        self.assertIsNone(report["native_partition_confirmed"])
        with self.assertRaises(NativeChunkError):
            inspect_native_chunks(source,require_native_partition=True)


class MultiActorNativeTests(unittest.TestCase):
    def setUp(self):
        self.anchor=bind_signed_gdd(gdd())
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database=Path(self.temp.name)/"source.db"

    def journal(self):
        journal=FrameReceiptJournal(self.database,self.anchor)
        ingest=GodotPhysicsCaptureIngestor(
            journal,candidate_digest=CANDIDATE,
            allowed_assets={"hero":A,"npc":B,"island":C})
        return journal,ingest

    def test_30_50_60_120_fps_multi_actor_runtime_chunk_migrations(self):
        for fps in (30,50,60,120):
            self.database=Path(self.temp.name)/f"frame{fps}.db"
            journal,ingestor=self.journal()
            with journal:
                first=ingestor.ingest(sample(0,self.anchor.source_digest,fps=fps))
                second=ingestor.ingest(sample(1,self.anchor.source_digest,fps=fps))
                self.assertEqual(second["frame"],1)
                self.assertEqual(len(second["native_chunk_evidence_digest"]),64)
                proof=journal.native_chunk_evidence(1)
                self.assertEqual(proof["chunk_count"],3)
                self.assertTrue(proof["native_partition_confirmed"])
                self.assertEqual(journal.load(1)[1]["cross_chunk_migrations"],1)
                self.assertEqual(journal.replay()["verified_frames"],2)
                journal.fork("undo0",through=0)
            with FrameReceiptJournal(self.database,self.anchor,track="undo0") as fork:
                self.assertEqual(fork.replay()["verified_frames"],1)
                self.assertEqual(fork.native_chunk_evidence(0)["actor_count"],3)

    def test_resume_only_accepts_exact_existing_records(self):
        journal,ingestor=self.journal()
        with journal:
            lines=[json.dumps(sample(i,self.anchor.source_digest))
                   for i in range(3)]
            first=ingestor.ingest_jsonl(lines)
            self.assertEqual(len(first),3)
            replay=ingestor.ingest_jsonl(lines,resume=True)
            self.assertTrue(all(x.get("reused_existing") for x in replay))
            self.assertEqual(journal.stats()["head"],2)
            extension=ingestor.ingest_jsonl(
                lines+[json.dumps(sample(3,self.anchor.source_digest))],
                resume=True)
            self.assertEqual(sum(not x.get("reused_existing",False) for x in extension),1)
            altered=sample(1,self.anchor.source_digest)
            altered["actors"][0]["contact_count"]=12
            with self.assertRaises(NativeObservationError):
                ingestor.ingest(altered,resume=True)
            self.assertEqual(journal.replay()["verified_frames"],4)

    def test_forged_partition_rejected_with_transaction_rollback(self):
        journal,ingestor=self.journal()
        with journal:
            with self.assertRaises(NativeObservationError):
                ingestor.ingest(sample(0,self.anchor.source_digest,corrupted=True))
            self.assertEqual(journal.stats()["head"],-1)
            self.assertEqual(journal.stats()["deduplicated_blobs"],0)
            ingestor.ingest(sample(0,self.anchor.source_digest))
            self.assertEqual(journal.replay()["verified_frames"],1)

    def test_corrupt_persisted_chunk_blob_breaks_replay(self):
        journal,ingestor=self.journal()
        with journal:
            proof=ingestor.ingest(sample(0,self.anchor.source_digest))
            identity=proof["native_chunk_evidence_digest"]
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                       (identity,))
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            with self.assertRaises(FrameJournalError):
                journal.replay()

    def test_exporter_multi_actor_only_from_verified_frame_source(self):
        cfg=scene_params()
        cfg.update(frame_gdd=self.anchor,frame_index=0,frame_objects=(
            FrameObject("hero",Vec3(0,0,30),Vec3(0,0,-20),A),
            FrameObject("npc",Vec3(-1,0,2),Vec3(0,0,0),B),
            FrameObject("island",Vec3(70,0,0),Vec3(0,0,0),C),
        ))
        candidate=compile_frontier_scene(**cfg)
        overlay=emit_frontier_godot_overlay(
            candidate,enable_native_capture=True,
            native_capture_all_actors=True,native_capture_max_frames=300)
        native=json.loads(overlay["frontier/data/scene.json"])["native_capture"]
        self.assertEqual(len(native["actors"]),3)
        self.assertEqual(native["actor_id"],"hero")
        self.assertEqual({a["id"] for a in native["actors"]},
                         {"hero","npc","island"})
        self.assertEqual({a["source_kind"] for a in native["actors"]},
                         {"native_rigid_reference","generated_source_proxy"})
        gd=overlay["frontier/frontier_scene.gd"]
        self.assertIn("_native_capture_nodes",gd)
        self.assertIn("NativeStaticSourceProxy",gd)
        self.assertIn("native_chunks",gd)
        self.assertIn("get_colliding_bodies()",gd)
        self.assertIn("chunks.sort_custom(_native_chunk_less)",gd)
        self.assertEqual(native["chunk_size_m"],32.)
        simple=emit_frontier_godot_overlay(
            candidate,enable_native_capture=True)
        self.assertEqual(len(json.loads(
            simple["frontier/data/scene.json"])["native_capture"]["actors"]),1)

    def test_exporter_fails_closed_without_runtime_provenance(self):
        candidate=compile_frontier_scene(**scene_params())
        with self.assertRaises(FrontierGodotError):
            emit_frontier_godot_overlay(candidate,enable_native_capture=True,
                                        native_capture_all_actors=True)


if __name__=="__main__":
    unittest.main()
