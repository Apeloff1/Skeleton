"""Constructed receipt regression contracts; no ROMs or native binaries involved."""
import copy
import unittest

from skeleton.jeeves.game_comparison_pairwise import (
    PairwiseObservationError, analyze_live_comparison_evidence,
    render_pairwise_observation_dashboard)
from skeleton.jeeves.game_comparison_schema import digest


def controller(button=0):
    return {"buttons": button, "axes": [0, 0, 0, 0], "keys": [],
            "mouse": [0, 0, 0, 0, 0, 0], "pointer": [0, 0, 0]}


def evidence(n=2):
    study, registry, source, core, environment = ("1"*64, "2"*64, "3"*64, "4"*64, "5"*64)
    lanes = {}
    for k in range(n):
        name = "game_" + str(k)
        first = digest(["skeleton.game.live_comparison.v1", study, name,
                        source, environment, registry, "reset", 7])
        last = first
        events = []
        for idx in range(1, 4):
            ports = [controller(1 if idx % 2 else 0)]
            receipt = {
                "schema_version": "skeleton.game.live_native_step_receipt.v1",
                "game_id": name, "index": idx, "episode_step": idx,
                "reset_generation": 0, "input_vector_sha256": digest(ports),
                "controller_ports": ports, "action_mode": "actual_native_controller_input",
                "frame_sha256": str((k + idx) % 10)*64, "pcm_sha256": "9"*64,
                "native_frame_calls": idx, "native_audio_frames": 256,
                "transition_sha256": "8"*64,
                "objective_observations": {
                    "screen_mean": idx / 5 + k / 100,
                    "visual_change": float(idx + k),
                    "audio_rms": idx / 10,
                    "step_fraction": idx / 256,
                },
                "source_content_sha256": source,
                "core_sha256": core, "previous_chain_sha256": last,
            }
            last = digest(receipt)
            receipt["receipt_sha256"] = last
            events.append({"event_kind": "native_step", "receipt": receipt,
                           "receipt_sha256": last})
        lanes[name] = {
            "game_id": name, "core_id": "pinned_core", "target_id": "nes",
            "source_media_sha256": source, "core_sha256": core,
            "native_environment_sha256": environment, "seed": 7,
            "initial_chain_sha256": first, "final_chain_sha256": last,
            "step_count": 3, "reset_count": 0, "native_events": events,
        }
    return {
        "schema_version": "skeleton.game.live_evidence_export.v1",
        "study_id": "controlled_study", "study_digest": study,
        "registry_digest": registry, "batch_index": 0, "lanes": lanes,
    }


class PairwiseNativeObservationContracts(unittest.TestCase):
    def test_two_lanes_descriptive_only(self):
        result = analyze_live_comparison_evidence(evidence())
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["total_input_steps"], 6)
        self.assertEqual(result["pairs"][0]["overlapping_episode_step_ordinals"], 3)
        self.assertIsNone(result["pairs"][0]["hardware_accuracy_winner"])
        self.assertEqual(result["lanes"][0]["active_input_steps"], 2)
        self.assertFalse(result["model_weights_updated"])
        page = render_pairwise_observation_dashboard(result)
        self.assertIn("Multi-emulator A/B observations", page)
        self.assertIn(result["analysis_sha256"], page)

    def test_ten_lanes_create_forty_five_pairs(self):
        report = analyze_live_comparison_evidence(evidence(10))
        self.assertEqual(report["lane_count"], 10)
        self.assertEqual(report["pair_count"], 45)
        self.assertEqual(report["total_input_steps"], 30)

    def test_invalid_frame_receipt_is_rejected(self):
        export = evidence()
        export["lanes"]["game_0"]["native_events"][0]["receipt"]["frame_sha256"] = "f"*64
        with self.assertRaises(PairwiseObservationError):
            analyze_live_comparison_evidence(export)

    def test_nonfinite_signal_is_rejected(self):
        export = evidence()
        export["lanes"]["game_1"]["native_events"][1]["receipt"]["objective_observations"]["audio_rms"] = float("nan")
        with self.assertRaises(PairwiseObservationError):
            analyze_live_comparison_evidence(export)

    def test_reset_is_new_ordinal_generation(self):
        export = evidence()
        for lane in export["lanes"].values():
            lane["native_events"] = lane["native_events"][:1]
            previous = lane["native_events"][-1]["receipt_sha256"]
            reset = {
                "schema_version": "skeleton.game.live_native_reset_receipt.v1",
                "game_id": lane["game_id"], "reset_generation": 1,
                "previous_chain_sha256": previous,
                "frame_sha256": "f"*64, "audio_sha256": "9"*64,
                "source_content_sha256": lane["source_media_sha256"],
                "seed_is_label_only": True,
            }
            previous = digest(reset)
            reset["receipt_sha256"] = previous
            lane["native_events"].append({
                "event_kind": "native_reset", "receipt": reset,
                "receipt_sha256": previous,
            })
            lane["step_count"], lane["reset_count"] = 1, 1
            lane["final_chain_sha256"] = previous
        report = analyze_live_comparison_evidence(export)
        self.assertEqual(report["pairs"][0]["overlapping_episode_step_ordinals"], 1)
        self.assertEqual([ep["steps"] for ep in report["lanes"][0]["episodes"]], [1, 0])

    def test_html_refuses_modified_report(self):
        report = analyze_live_comparison_evidence(evidence())
        bad = copy.deepcopy(report)
        bad["pairs"][0]["hardware_accuracy_winner"] = "game_0"
        with self.assertRaises(PairwiseObservationError):
            render_pairwise_observation_dashboard(bad)

    def test_cannot_claim_more_than_ten_native_lanes(self):
        with self.assertRaises(PairwiseObservationError):
            analyze_live_comparison_evidence(evidence(11))


if __name__ == "__main__":
    unittest.main()
