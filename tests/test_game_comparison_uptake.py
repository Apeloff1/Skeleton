"""Source-contract tests for native evidence audit; uses synthetic fixtures only."""
from __future__ import annotations
import unittest
from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_comparison_uptake import (
    build_comparison_uptake_audit, ComparisonUptakeError,
)


def fixture():
    game_id="synthetic_game"
    src=digest(["source_game"])
    actions=["idle","right","a"]
    previous=digest(["comparative-native-session",game_id,src])
    steps=[]
    phases={}
    for index,action in enumerate(actions,1):
        entry={
            "step":index,"action":action,
            "native_frame_sha256":digest(["frame",index]),
            "native_pcm_sha256":digest(["audio",index]),
            "native_frame_count":index,
            "native_audio_frames":100,
            "transition_sha256":digest(["transition",index]),
            "objective_observations":{"visual_change":0.1,"audio_rms":0.2,
                                      "screen_mean":.3,"step_fraction":index/3},
            "input_protocol":"approved_libretro_policy_action",
            "gameplay_success_verified":False,
        }
        previous=digest([previous,entry])
        entry["receipt_chain_sha256"]=previous
        steps.append(entry)
        phases[("earlier","middle","after")[index-1]]={
            "step":index,"source":"actual_isolated_libretro",
            "action_at_checkpoint":action,
            "controller_input_receipt_sha256":previous,
            "frame_sha256":entry["native_frame_sha256"],
            "audio_sha256":entry["native_pcm_sha256"],
            "transition_sha256":entry["transition_sha256"],
            "evidence_sha256":digest(["checkpoint",index]),
        }
    return {
        "schema_version":"skeleton.game.comparative_study_result.v1",
        "study_id":"synthetic_only", "study_manifest_sha256":digest(["manifest"]),
        "games":{
            game_id:{
                "status":"actual_native_observations_captured",
                "source_sha256":src,"source_bundle_sha256":src,
                "native_session_event_receipts":steps,
                "native_session_log_digest":previous,
                "native_session_log_steps":3,
                "phases":phases,
                "canonical_offline_trace_sha256":digest(["trace"]),
            }
        },
        "observer_notes":[],
    }


class ComparativeUptakeContractTests(unittest.TestCase):
    def test_recalculates_all_steps_and_phase_bindings(self):
        report=build_comparison_uptake_audit(fixture())
        self.assertEqual(report["measured_summary"]["native_steps_reverified"],3)
        self.assertEqual(report["measured_summary"]["production_llm_parameter_updates"],0)
        self.assertFalse(report["review_gate"]["ready_for_production_promotion"])

    def test_reject_modified_frame_hash(self):
        source=fixture()
        source["games"]["synthetic_game"]["native_session_event_receipts"][0]["native_frame_sha256"]="0"*64
        with self.assertRaises(ComparisonUptakeError):
            build_comparison_uptake_audit(source)

    def test_reject_modified_stage_step(self):
        source=fixture()
        source["games"]["synthetic_game"]["phases"]["middle"]["action_at_checkpoint"]="b"
        with self.assertRaises(ComparisonUptakeError):
            build_comparison_uptake_audit(source)

if __name__=="__main__":
    unittest.main()
