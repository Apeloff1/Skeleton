"""Native Godot JSONL smoke acceptance; executable with real input or synthetic checks."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.validate_game_frontier_native_smoke import (
    validate_native_trace, NativeSmokeError, main,
)
from tests.test_game_frontier_native_chunks import sample
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from tests.test_game_frontier_position_frames import gdd


class NativeObservedSmokeTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.capture=self.root/"physics.jsonl"
        self.scene=self.root/"scene.json"
        self.gdd=bind_signed_gdd(gdd())
        self.scene_body={
            "schema":"skeleton.game.frontier_godot_overlay.v1",
            "origin_candidate_digest":"d"*64,
            "native_capture":{
                "enabled":True,"fps":60,"candidate_digest":"d"*64,
                "gdd_digest":self.gdd.source_digest,
                "actor_id":"hero","actor_asset_digest":"a"*64,
                "chunk_size_m":32.,
                "actors":[
                    {"id":"hero","source_digest":"a"*64},
                    {"id":"npc","source_digest":"b"*64},
                    {"id":"island","source_digest":"c"*64},
                ],
            },
        }
        self.scene.write_text(json.dumps(self.scene_body))
        self.records=[sample(i,self.gdd.source_digest) for i in range(6)]
        self.record()

    def record(self):
        self.capture.write_text("".join(json.dumps(x)+"\n" for x in self.records))

    def test_proves_source_tick_motion_chunk_and_contacts(self):
        result=validate_native_trace(self.capture,self.scene)
        self.assertEqual(result["fixed_physics_ticks_observed"],6)
        self.assertEqual(result["actors_observed_each_tick"],3)
        self.assertEqual(result["controlled_actor"],"hero")
        self.assertGreater(result["controlled_displacement_m"],.01)
        self.assertGreaterEqual(result["cross_chunk_migrations_observed"],1)
        self.assertEqual(result["positive_contact_count_observations"],6)
        self.assertEqual(len(result["receipt_digest"]),64)

    def test_rejects_missing_runtime_actor_or_wrong_scene(self):
        modified=deepcopy(self.records)
        modified[1]["actors"].pop()
        self.records=modified
        self.record()
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)
        self.scene_body["native_capture"]["candidate_digest"]="f"*64
        self.scene.write_text(json.dumps(self.scene_body))
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)

    def test_refuses_fake_nonmoving_rigidbody_or_incomplete_ticks(self):
        modified=deepcopy(self.records)
        for tick in modified:
            tick["actors"][0]["world_xyz_m"]=[31.99,-1,30]
            tick["actors"][0]["velocity_xyz_mps"]=[0,0,0]
        self.records=modified
        self.record()
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)
        self.records=self.records[:2]
        self.record()
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)

    def test_rejects_forged_chunk_monotone_time_and_contact(self):
        for field, bad in (
            ("native_chunks",[]),
            ("ticks_usec",-1),
            ("native_tick",15),
        ):
            updated=deepcopy(self.records)
            updated[2][field]=bad
            self.records=updated
            self.record()
            with self.assertRaises(NativeSmokeError):
                validate_native_trace(self.capture,self.scene)
            self.records=[sample(i,self.gdd.source_digest) for i in range(6)]
        updated=deepcopy(self.records)
        updated[2]["actors"][0]["contact_count"]=-1
        self.records=updated
        self.record()
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)

    def test_rejects_bounds_oversize_line_and_unqualified_permissions(self):
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene,min_ticks=0)
        self.capture.write_text("X"*150000+"\n")
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)
        self.records=[sample(i,self.gdd.source_digest) for i in range(6)]
        self.record()
        altered=dict(self.scene_body)
        altered["native_capture"]=dict(self.scene_body["native_capture"],enabled=False)
        self.scene.write_text(json.dumps(altered))
        with self.assertRaises(NativeSmokeError):
            validate_native_trace(self.capture,self.scene)


if __name__=="__main__":
    unittest.main()
