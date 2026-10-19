"""Independent game-instrument audits and forged-trace adversarial cases."""
from copy import deepcopy
import json
import math
import unittest

from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_instrument_trace import (
    verify_native_instrument_trace,
)
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError


class NativeInstrumentTraceTests(NativeQuestBatchTests):
    def source_trace(self):
        data=[]
        for i in range(self.journal.stats()["head"]+1):
            sample=self.journal.native_sample(i)
            actor=next(a for a in sample["actors"] if a["id"]=="hero")
            x,y,z=actor["velocity_xyz_mps"]
            ground=math.hypot(x,y)
            data.append({
                "schema":"skeleton.game.godot_native_instrument_sample.v1",
                "authority":"independent_native_instrument_observation_not_attested",
                "signed_gdd_digest":self.journal.gdd.source_digest,
                "scene_candidate_digest":"d"*64,
                "actor_id":"hero","native_tick":i,"fps":sample["fps"],
                "world_xyz_m":actor["world_xyz_m"],
                "velocity_xyz_mps":actor["velocity_xyz_mps"],
                "ground_speed_mps":ground,
                "vertical_rate_mps":z,
                "heading_deg":math.degrees(math.atan2(x,y))%360 if ground>1e-7 else 0.,
                "airflow_xyz_mps":[0.,0.,0.],
                "air_relative_speed_mps":math.sqrt(x*x+y*y+z*z),
                "contact_count":actor["contact_count"],
            })
        return data

    def verify(self,rows):
        return verify_native_instrument_trace(
            self.journal,(json.dumps(x) for x in rows),
            actor_id="hero",scene_candidate_digest="d"*64,
            expected_airflow_xyz_mps=[0.,0.,0.],
            expected_fps=self.journal.native_sample(0)["fps"])

    def test_independently_replayed_all_frames(self):
        actual=self.verify(self.source_trace())
        self.assertEqual(actual["verified_physics_frames"],5)
        self.assertEqual(actual,self.verify(self.source_trace()))
        self.assertEqual(len(actual["instrument_chain_head"]),64)
        self.assertEqual(len(actual["receipt_digest"]),64)

    def test_missing_duplicate_or_out_of_order_frame_rejected(self):
        source=self.source_trace()
        for altered in (source[1:],source[:-1],source+[source[-1]],
                        list(reversed(source))):
            with self.subTest(length=len(altered)),self.assertRaises(NativeQuestSessionError):
                self.verify(altered)

    def test_forged_hud_measurements_source_and_boundaries_rejected(self):
        source=self.source_trace()
        forged_fields=[
            ("ground_speed_mps",1000.),
            ("vertical_rate_mps",-999.),
            ("heading_deg",270.1),
            ("air_relative_speed_mps",999.),
            ("world_xyz_m",[900.,800.,700.]),
            ("velocity_xyz_mps",[10.,20.,30.]),
            ("airflow_xyz_mps",[3.,4.,5.]),
            ("contact_count",999),
            ("actor_id","intruder"),
            ("scene_candidate_digest","1"*64),
        ]
        for key,value in forged_fields:
            mutated=deepcopy(source)
            mutated[0][key]=value
            with self.subTest(key=key),self.assertRaises(NativeQuestSessionError):
                self.verify(mutated)

    def test_nan_overflow_and_invalid_schema_rejected(self):
        for key,value in (("ground_speed_mps",float("nan")),
                          ("heading_deg",float("inf")),
                          ("native_tick",True)):
            source=self.source_trace()
            source[0][key]=value
            with self.subTest(key=key),self.assertRaises(NativeQuestSessionError):
                self.verify(source)
