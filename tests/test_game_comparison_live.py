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

    def snapshot(self):
        return {
            "steps":self._n,
            "state_sha256":digest(["synthetic-savestate",self._name,self._n]),
            "snapshot_digest":digest(["synthetic-snapshot",self._name,self._n]),
            "frame":dict(self._frame),
            "synthetic_private_state":{"n":self._n},
        }

    def restore(self, snapshot):
        self._n=snapshot["synthetic_private_state"]["n"]
        self._frame_at("reset" if self._n==0 else "step")

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

    def test_terminal_game_does_not_overrun_burst(self):
        session=self._session()
        env=self.running[0]
        base=env.input_step
        def terminal_step(controls):
            result=base(controls)
            env.done=env._n>=2
            return result
        env.input_step=terminal_step
        controls={"buttons":0,"axes":[0,0,0,0],"keys":[],
                  "mouse":[0]*6,"pointer":[0]*3}
        result=session.step({"steps":[
            {"game_id":"first","controls":[controls],"repeat":8},
        ]})
        row=result["results"][0]
        self.assertEqual(row["completed_native_steps"],2)
        self.assertTrue(row["stopped_on_episode_boundary"])
        self.assertEqual(row["status"],"episode_complete")
        self.assertIsNotNone(row["native_preview"])
        self.assertEqual(verify_live_evidence(session.export_evidence())[
            "total_real_reported_native_steps"],2)

    def test_cross_device_input_is_rejected_atomically(self):
        session=self._session()
        keyboard_only={"buttons":0,"axes":[0,0,0,0],"keys":[13],
                       "mouse":[0]*6,"pointer":[0]*3}
        with self.assertRaises(LiveComparisonError):
            session.step({"steps":[
                {"game_id":"first","controls":[keyboard_only]},
                {"game_id":"second","controls":[keyboard_only]},
            ]})
        self.assertEqual(sum(x["step_count"] for x in session.export_evidence()[
            "lanes"].values()),0)

    def test_core_replacement_invalidates_export_verification(self):
        session=self._session()
        controls={"buttons":0,"axes":[0,0,0,0],"keys":[],
                  "mouse":[0]*6,"pointer":[0]*3}
        session.step({"steps":[{"game_id":"first","controls":[controls]}]})
        exported=session.export_evidence()
        exported["lanes"]["first"]["core_sha256"]="0"*64
        with self.assertRaises(LiveEvidenceError):
            verify_live_evidence(exported)

    def test_private_native_checkpoint_rewind_and_branch_evidence(self):
        session=self._session()
        input_ports={"buttons":1,"axes":[0,0,0,0],"keys":[],
                     "mouse":[0]*6,"pointer":[0]*3}
        session.step({"steps":[{"game_id":"first","controls":[input_ports],"repeat":2}]})
        checkpoint=session.checkpoint("first")
        self.assertEqual(checkpoint["episode_step"],2)
        self.assertNotIn("state_base64",checkpoint)
        self.assertFalse(checkpoint["private_savestate_bytes_returned"])
        session.step({"steps":[{"game_id":"first","controls":[input_ports],"repeat":2}]})
        rewind=session.rewind("first")
        self.assertEqual(rewind["restored_episode_step"],2)
        self.assertEqual(rewind["checkpoint_id"],1)
        session.step({"steps":[{"game_id":"first","controls":[input_ports]}]})
        packet=session.export_evidence()
        self.assertFalse(packet["private_savestates_exported"])
        self.assertNotIn("state_base64",json.dumps(packet))
        audited=verify_live_evidence(packet)
        row=next(x for x in audited["games"] if x["game_id"]=="first")
        self.assertEqual(row["native_checkpoints_verified"],1)
        self.assertEqual(row["native_rewinds_verified"],1)
        self.assertEqual(row["native_input_steps_verified"],5)
        self.assertTrue(row["snapshot_based_episodes_require_separate_qualification"])
        self.assertEqual(row["replayable_controller_tapes"],[])
        self.assertEqual(audited["total_native_checkpoint_events"],1)
        self.assertEqual(audited["total_native_rewind_events"],1)

    def test_branch_difference_report_aligns_actual_native_input_after_rewind(self):
        from skeleton.jeeves.game_comparison_branch_analysis import (
            build_live_branch_difference_report,
        )
        session=self._session()
        base={"buttons":1,"axes":[0,0,0,0],"keys":[],
              "mouse":[0]*6,"pointer":[0]*3}
        altered={"buttons":256,"axes":[0,0,0,0],"keys":[],
                 "mouse":[0]*6,"pointer":[0]*3}
        session.checkpoint("first")
        session.step({"steps":[{"game_id":"first","controls":[base],"repeat":2}]})
        session.rewind("first")
        session.step({"steps":[{"game_id":"first","controls":[altered]}]})
        report=build_live_branch_difference_report(session.export_evidence())
        game=next(row for row in report["games"] if row["game_id"]=="first")
        self.assertEqual(game["verified_rewind_count"],1)
        branch=game["branch_comparisons"][0]
        self.assertEqual(branch["original_path_native_steps"],2)
        self.assertEqual(branch["rewound_path_native_steps"],1)
        self.assertEqual(branch["first_controller_difference_offset"],1)
        # This fixture's frame depends on step index, not the action input.
        # Different input alone never qualifies a native visual effect.
        self.assertIsNone(branch["first_video_difference_offset"])
        self.assertFalse(branch["change_in_game_mechanics_or_training_proven"])
        self.assertFalse(report["native_snapshot_game_memory_or_pcm_exported"])

    def test_branch_report_rejects_modified_native_snapshot_sha_chain(self):
        from skeleton.jeeves.game_comparison_branch_analysis import (
            build_live_branch_difference_report,
        )
        session=self._session()
        session.checkpoint("first")
        session.rewind("first")
        export=session.export_evidence()
        export["lanes"]["first"]["native_events"][0]["receipt"]["native_state_sha256"]="0"*64
        with self.assertRaises(LiveEvidenceError):
            build_live_branch_difference_report(export)

    def test_private_snapshot_invalid_after_native_reset(self):
        session=self._session()
        session.checkpoint("first")
        session.reset("first")
        with self.assertRaises(LiveComparisonError):
            session.rewind("first")
        audited=verify_live_evidence(session.export_evidence())
        self.assertEqual(audited["total_native_checkpoint_events"],1)
        self.assertEqual(audited["total_native_reset_events"],1)
        self.assertEqual(audited["total_native_rewind_events"],0)

    def test_tampered_native_checkpoint_receipt_fails_closed(self):
        session=self._session()
        session.checkpoint("first")
        packet=session.export_evidence()
        packet["lanes"]["first"]["native_events"][0]["receipt"]["native_state_sha256"]="0"*64
        with self.assertRaises(LiveEvidenceError):
            verify_live_evidence(packet)

    def test_checkpoint_and_rewind_have_strict_finite_caps(self):
        session=self._session()
        session.checkpoint("first")
        session.checkpoint("first")
        with self.assertRaises(LiveComparisonError):
            session.checkpoint("first")
        session.rewind("first")
        session.rewind("first")
        with self.assertRaises(LiveComparisonError):
            session.rewind("first")
        self.assertEqual(verify_live_evidence(session.export_evidence())[
            "total_native_rewind_events"],2)

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

    def test_native_pcm_excerpt_bounded_and_visible_below_controller(self):
        import base64
        from skeleton.jeeves.game_comparison_live import _preview
        session=self._session()
        lane=session._lanes["first"]
        pcm=bytes([0,1,2,3])*32
        def generated_native_audio():
            return {
                "data_uri":"data:image/png;base64,iVBORw0KGgo=",
                "audio":{
                    "samples_base64":base64.b64encode(pcm).decode(),
                    "sample_frames":32,"sample_rate":16000,"channels":2,
                    "sample_digest":"a"*64,"source_digest":"b"*64,
                },
            }
        lane.env.preview=generated_native_audio
        data=_preview(lane.env)
        excerpt=data["recent_native_pcm_preview"]
        self.assertEqual(excerpt["sample_frames"],32)
        self.assertEqual(excerpt["sample_rate"],16000)
        self.assertTrue(excerpt["actual_native_audio_not_original_music"])
        page=render_live_comparison_page("a"*64,"b"*32)
        self.assertIn("Listen to bounded native PCM",page)
        self.assertLess(page.index("root.append(deckFor(id));"),
                        page.index("root.append(nativeAudioMonitor(frame));"))

    def test_browser_uses_below_screen_controllers(self):
        page=render_live_comparison_page("a"*64,"b"*32)
        self.assertIn("root.append(stage);",page)
        self.assertIn("root.append(deckFor(id));",page)
        self.assertIn("X-Study-Token",page)
        self.assertIn('nonce="bbbb',page)


if __name__=="__main__":
    unittest.main()
