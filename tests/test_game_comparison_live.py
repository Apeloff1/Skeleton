"""Source-level live emulator desk tests with fake cores (not hardware proof)."""
from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_comparison_live import LiveComparison, LiveComparisonError
from skeleton.jeeves.game_comparison_live_evidence import verify_live_evidence, LiveEvidenceError
from skeleton.jeeves.game_comparison_live_viewer import render_live_comparison_page


def fixture():
    def game(name, idx):
        return {
            "id":name, "title":name,
            "series_id":"original_testing",
            "release_order":idx,"release_year":2025,
            "series_phase":"earlier" if idx==1 else "middle",
            "target_id":"nes","core_id":"fceumm",
            "source_path":"/private/"+name+".nes",
            "source_sha256":digest(["fake",name]),
            "rights_evidence_digest":digest(["rights",name]),
            "actions":["idle","right","a"],
            "seed":123,"frames_per_step":1,
            "controller_devices":["joypad"],
        }
    return {"schema_version":"skeleton.game.comparative_study.v1",
            "study_id":"synthetic_live_only","title":"Synthetic, no ROM",
            "games":[game("first",1),game("second",2)],
            "pairs":[{"left_id":"first","right_id":"second","questions":[]}],
            "notes":[],"max_active":2}


class FakeNativeEnv:
    """Only a fixture; no libretro worker, ROM or hardware involved."""
    def __init__(self, name):
        self._name=name
        self._n=0
        self._closed=False
        self.spec=SimpleNamespace(environment_digest=digest(["environment",name]))
        self.core=SimpleNamespace(library_sha256=digest(["core",name]))
        self._frame={}
        self.done=False

    def _frame_at(self, stage):
        self._frame={
            "pixel_sha256":digest(["pixels",self._name,self._n,stage]),
            "audio_sha256":digest(["pcm",self._name,self._n,stage]),
            "audio_frames":0,"runs":self._n+1,
            "video_callbacks":1,"width":32,"height":32,"rotation":0,
        }

    def reset(self, seed):
        self._n=0
        self._frame_at("reset")

    def input_step(self, controls):
        self._n+=1
        self._frame_at("step")
        evidence_digest=digest(["native-step",self._name,self._n,controls])
        return SimpleNamespace(
            observation={
                "screen_mean":.2,"visual_change":.3,
                "audio_rms":.1,"step_fraction":self._n/64,
            },
            transition_digest=evidence_digest,
        )

    def preview(self):
        return {"data_uri":"data:image/png;base64,iVBORw0KGgo="}

    def close(self):
        self._closed=True


class NativeLiveComparisonContracts(unittest.TestCase):
    def setUp(self):
        from skeleton.jeeves import game_comparison_live as live
        self.module=live
        self.running=[]
        self.patches=[
            patch.object(live,"GameEmulatorRegistry"),
            patch.object(live,"prepare_comparison_media"),
            patch.object(live,"create_emulator_environment"),
            patch.object(live,"_storage_waves"),
        ]
        self.mock_registry,self.mock_media,self.mock_create,self.mock_disk=[
            p.start() for p in self.patches
        ]
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
        reg=self.mock_registry.from_environment.return_value
        reg.registry_digest=digest(["approved-registry"])
        reg.resolve_core.return_value=SimpleNamespace(target_ids=("nes",))
        self.mock_media.side_effect=lambda g:(
            {"rom_source":bytes([1]),"filename":g["id"]+".nes"},g["source_sha256"]
        )
        self.mock_disk.side_effect=lambda games,**kw:([games],1000000000)
        def create(target,**kwargs):
            env=FakeNativeEnv(kwargs["filename"])
            self.running.append(env)
            return env
        self.mock_create.side_effect=create

    def _session(self):
        session=LiveComparison(fixture(),batch_index=0,max_steps=12)
        self.addCleanup(session.close)
        return session

    def test_two_native_lanes_and_verifiable_reset_chain(self):
        session=self._session()
        state=session.state()
        self.assertEqual(len(state["lanes"]),2)
        self.assertTrue(all(x["native_preview"]["frame_sha256"] for x in state["lanes"].values()))
        controls={"buttons":256,"axes":[0,0,0,0],
                  "keys":[],"mouse":[0]*6,"pointer":[0]*3}
        result=session.step({"steps":[
            {"game_id":"first","controls":[controls]},
            {"game_id":"second","controls":[controls]},
        ]})
        self.assertTrue(result["all_succeeded"])
        session.reset("first")
        session.step({"steps":[{"game_id":"first","controls":[controls]}]})
        export=session.export_evidence()
        audited=verify_live_evidence(export)
        self.assertEqual(audited["total_real_reported_native_steps"],3)
        row=next(g for g in audited["games"] if g["game_id"]=="first")
        self.assertEqual(row["episode_tape_lengths"],[1,1])
        self.assertEqual(row["native_resets_verified"],1)
        self.assertFalse(row["independently_attested_native_run"])

    def test_multi_step_burst_is_individually_receipted(self):
        session=self._session()
        controls={"buttons":1,"axes":[0,0,0,0],"keys":[],
                  "mouse":[0]*6,"pointer":[0]*3}
        result=session.step({"steps":[
            {"game_id":"first","controls":[controls],"repeat":4},
            {"game_id":"second","controls":[controls],"repeat":4},
        ]})
        self.assertTrue(result["all_succeeded"])
        self.assertEqual([x["completed_native_steps"] for x in result["results"]],[4,4])
        audited=verify_live_evidence(session.export_evidence())
        self.assertEqual(audited["total_real_reported_native_steps"],8)
        self.assertEqual(audited["total_native_reset_events"],0)

    def test_over_budget_burst_is_rejected_before_execution(self):
        session=self._session()
        controls={"buttons":0,"axes":[0,0,0,0],"keys":[],
                  "mouse":[0]*6,"pointer":[0]*3}
        with self.assertRaises(LiveComparisonError):
            session.step({"steps":[{"game_id":"first","controls":[controls],"repeat":9}]})
        self.assertEqual(session.export_evidence()["lanes"]["first"]["step_count"],0)

    def test_bad_port_fails_before_any_native_step(self):
        session=self._session()
        initial=session.export_evidence()
        with self.assertRaises(ValueError):
            session.step({"steps":[
                {"game_id":"first","controls":[{"buttons":65536}]},
                {"game_id":"second","controls":[]},
            ]})
        self.assertEqual(session.export_evidence(),initial)

    def test_corrupt_reset_receipt_is_rejected(self):
        session=self._session()
        session.reset("first")
        packet=session.export_evidence()
        packet["lanes"]["first"]["native_events"][0]["receipt"]["frame_sha256"]="0"*64
        with self.assertRaises(LiveEvidenceError):
            verify_live_evidence(packet)

    def test_ten_lane_limit_and_study_batch_restriction(self):
        with self.assertRaises(LiveComparisonError):
            LiveComparison(fixture(),batch_index=100)
        with self.assertRaises(LiveComparisonError):
            LiveComparison(fixture(),batch_index=0,game_ids=["first","first"])

    def test_browser_uses_below_screen_controllers(self):
        page=render_live_comparison_page("a"*64,"b"*32)
        self.assertIn("root.append(stage);",page)
        self.assertIn("root.append(deckFor(id));",page)
        self.assertIn("X-Study-Token",page)
        self.assertIn('nonce="bbbb',page)


if __name__=="__main__":
    unittest.main()
