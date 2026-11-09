"""Actual ten-run mirror room: ten multispectral projections per observed run.

No physically sensed wavelengths, thermal imager, pixel-depth mapper or
latent neural model is presumed. Audits operate on independently replayed
source-registered game engine episodes and reject modified evidence.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_scenario_lab import (
    ANGLES, MAX_LANES, mirrored_simulations, mirrored_rule_comparison,
)
from skeleton.jeeves.game_studio_multispectral import (
    BANDS, CHECKS, MultispectralAuditError, audit_simulation,
)


class TenRunMirrorRoomTests(unittest.TestCase):
    def setUp(self):
        self.source = make_studio_source(
            "economy", {"market_nodes":3,"goods":10},
            actions=("inspect","survey","wait","buy:1","sell:1"),
        )

    def test_ten_independent_simulations_with_ten_checks_and_ten_bands(self):
        self.assertEqual(MAX_LANES,10)
        self.assertEqual(len(ANGLES),10)
        self.assertEqual(len(BANDS),10)
        self.assertEqual(len(CHECKS),10)
        result=mirrored_simulations(self.source,seed=9,steps=3,workers=4)
        self.assertEqual(result["concurrent_reference_simulations_executed"],10)
        self.assertEqual(result["scrutiny_checked_runs"],10)
        self.assertEqual(result["scrutiny_checks_per_run"],10)
        self.assertEqual(result["workers_used"],4)
        self.assertFalse(result["actual_spectral_sensor_hardware"])
        self.assertEqual(result["multispectral_analysis_channels"],list(BANDS))
        self.assertEqual(len(result["lanes"]),10)
        for index,lane in enumerate(result["lanes"]):
            with self.subTest(angle=lane["angle"]):
                self.assertEqual(lane["angle"],ANGLES[index])
                self.assertEqual(lane["seed"],9+index)
                self.assertTrue(lane["audit_passed"])
                self.assertGreaterEqual(lane["steps"],1)
                self.assertFalse(lane["native_frames"])
                proof=lane["multispectral"]
                self.assertEqual(proof["passed_count"],10)
                self.assertEqual(proof["failed_count"],0)
                self.assertEqual([x["name"] for x in proof["checks"]],list(CHECKS))
                self.assertTrue(all(x["passed"] for x in proof["checks"]))
                self.assertFalse(proof["real_rgb_depth_thermal_sensors"])
                self.assertFalse(proof["real_visual_cameras"])
                self.assertFalse(proof["independent_information_streams_claimed"])
                self.assertEqual(set(proof["spectral_channels"]),set(BANDS))
                self.assertGreaterEqual(len(proof["reverse_checkpoints"]),2)
                for band in proof["spectral_channels"].values():
                    self.assertEqual(len(band["values"]),lane["steps"])
                    self.assertEqual(band["derivation"],
                                     "original_game_numeric_state_and_action_evidence")
                    self.assertEqual(len(band["digest"]),64)
                self.assertEqual(
                    audit_simulation(self.source,lane,steps=3),proof,
                )

    def test_tampered_source_and_trace_are_rejected_before_training(self):
        original=mirrored_simulations(
            self.source,seed=15,steps=3,workers=2,
            angles=("explore","temporal"),
        )
        lane=original["lanes"][0]
        tampered=deepcopy(lane)
        tampered["transition_digests"][0]="0"*64
        with self.assertRaises(MultispectralAuditError):
            audit_simulation(self.source,tampered,steps=3)
        altered_source=make_studio_source(
            "economy", {"market_nodes":3,"goods":10,"trade_tax":13},
            actions=("inspect","survey","wait","buy:1","sell:1"),
        )
        with self.assertRaises(MultispectralAuditError):
            audit_simulation(altered_source,lane,steps=3)
        forged=deepcopy(lane)
        forged["last_observation"]["score"]+=1.0
        with self.assertRaises(MultispectralAuditError):
            audit_simulation(self.source,forged,steps=3)
        forged=deepcopy(lane)
        forged["actions"].append("__foreign_python_action__")
        forged["steps"]+=1
        with self.assertRaises(MultispectralAuditError):
            audit_simulation(self.source,forged,steps=4)

    def test_all_ten_angles_are_repeatable_without_claiming_new_hardware(self):
        first=mirrored_simulations(self.source,seed=40,steps=2,workers=4)
        parallelism_changed=mirrored_simulations(self.source,seed=40,steps=2,workers=1)
        self.assertEqual(
            [lane["digest"] for lane in first["lanes"]],
            [lane["digest"] for lane in parallelism_changed["lanes"]],
        )

    def test_ten_angle_paired_candidate_scrutiny_is_source_matched(self):
        candidate=make_studio_source(
            "economy",{"market_nodes":3,"goods":10,"trade_tax":12},
            actions=("inspect","survey","wait","buy:1","sell:1"),
        )
        report=mirrored_rule_comparison(
            self.source,candidate,seed=20,steps=3,angles=ANGLES,
        )
        self.assertEqual(len(report["mirrors"]),10)
        self.assertFalse(report["source_promotion_authorized"])
        self.assertFalse(report["claimed_exhaustive_game_state_coverage"])
        self.assertGreater(report["total_replayed_action_applications"],0)
        self.assertEqual(len(report["digest"]),64)


if __name__=="__main__":
    unittest.main()
