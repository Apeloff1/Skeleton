"""All-family studio laboratory regression and actual mirrored execution tests.

The declaration manifest is not itself a completed certification. These tests
exercise the canonical registered source/run/restore path and demonstrate
bounded concurrency. Production/hardware and commercial game quality checks
need independent release gates.
"""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import ENGINES
from skeleton.jeeves.game_studio_environment import (
    StudioGameEnvironment, make_studio_source,
)
from skeleton.jeeves.game_studio_scenario_lab import (
    ANGLES, CHARTS, MOTIFS, ScenarioLabError,
    sales_informed_catalog, test_manifest, all_engine_test_manifests,
    propose_scenarios, mirrored_simulations, mirrored_rule_comparison,
)
from skeleton.jeeves.game_studio_rule_curriculum import apply_rule_proposal


class StudioEngineScenarioLabTests(unittest.TestCase):
    def test_every_engine_has_exhaustive_registered_control_test_matrix(self):
        self.assertEqual(len(ENGINES),43)
        all_rows=all_engine_test_manifests()
        self.assertEqual(all_rows["count"],43)
        self.assertFalse(all_rows["passed"])
        self.assertEqual(len(all_rows["engines"]),43)
        for editor in ENGINES:
            with self.subTest(editor=editor):
                manifest=test_manifest(editor)
                self.assertEqual(manifest["engine"],editor)
                self.assertEqual(manifest["angles"],list(ANGLES))
                self.assertEqual(manifest["registered_action_count"],
                                 len(manifest["registered_actions"]))
                self.assertGreater(manifest["registered_action_count"],0)
                self.assertGreater(len(manifest["field_axes"]),0)
                self.assertEqual(manifest["execution_status"],"not_run")
                self.assertEqual(manifest["verified_passes"],0)
                self.assertFalse(manifest["combinatorial_state_exhaustiveness_claimed"])
                self.assertGreaterEqual(len(manifest["mandatory_checks"]),15)
                self.assertTrue(all(row["required"] for row in manifest["mandatory_checks"]))
                for field in manifest["field_axes"]:
                    self.assertGreater(len(field["cases"]),0)
                    self.assertIn("invalid_value_rejection",field["checks"])

    def test_six_actual_mirrors_execute_different_perspectives_concurrently(self):
        source=make_studio_source("economy", {"market_nodes":3,"goods":10})
        report=mirrored_simulations(source,seed=6,steps=6,workers=4)
        self.assertEqual(report["concurrent_reference_simulations_executed"],6)
        self.assertEqual(report["workers_used"],4)
        self.assertEqual(report["angles"],list(ANGLES))
        self.assertFalse(report["training_candidate_mutated"])
        self.assertEqual(report["view_kind"],
                         "sampled_reference_telemetry_not_native_game_frames")
        for i,lane in enumerate(report["lanes"]):
            with self.subTest(angle=lane["angle"]):
                self.assertEqual(lane["angle"],ANGLES[i])
                self.assertEqual(lane["seed"],6+i)
                self.assertTrue(1<=lane["steps"]<=6)
                self.assertLessEqual(len(lane["frames"]),5)
                self.assertEqual(len(lane["transition_digests"]),lane["steps"])
                self.assertEqual(len(lane["actions"]),lane["steps"])
                self.assertFalse(lane["native_frames"])
                self.assertEqual(len(lane["snapshot_digest"]),64)
                self.assertTrue(all(isinstance(x,str) for x in lane["actions"]))
        repeat=mirrored_simulations(source,seed=6,steps=6,workers=2)
        # Parallel order and worker count cannot change engine source/trace
        # and observation receipts.  Worker count itself is metadata.
        self.assertEqual(
            [x["digest"] for x in repeat["lanes"]],
            [x["digest"] for x in report["lanes"]],
        )

    def test_paired_all_angle_evaluation_is_original_source_bound(self):
        source=make_studio_source("economy",{"market_nodes":3,"goods":10})
        other=make_studio_source("economy",{"market_nodes":3,"goods":10,
                                          "trade_tax":15})
        comparison=mirrored_rule_comparison(source,other,seed=10,steps=3,
                                           angles=ANGLES)
        self.assertEqual(len(comparison["mirrors"]),6)
        self.assertFalse(comparison["source_promotion_authorized"])
        self.assertTrue(comparison["independent_human_review_required"])
        self.assertEqual(len(comparison["digest"]),64)
        self.assertNotEqual(comparison["baseline_source_digest"],
                            comparison["candidate_source_digest"])
        for i,row in enumerate(comparison["mirrors"]):
            self.assertEqual(row["angle"],ANGLES[i])
            self.assertEqual(row["seed"],10+i)
            self.assertEqual(len(row["baseline_evidence_digest"]),64)
            self.assertEqual(len(row["candidate_evidence_digest"]),64)
        same=mirrored_rule_comparison(source,source,seed=10,steps=3)
        self.assertEqual(same["worst_return_difference"],0.0)
        self.assertEqual(same["mean_return_difference"],0.0)
        with self.assertRaises(ScenarioLabError):
            mirrored_rule_comparison(
                source,make_studio_source("animation"),seed=10,steps=2,
            )

    def test_readonly_mirrors_do_not_mutate_original_game_source(self):
        source=make_studio_source("save_system")
        before=deepcopy(source)
        views=mirrored_simulations(source,angles=("safety","boundary"),
                                  seed=12,steps=5,workers=2)
        self.assertEqual(source,before)
        self.assertEqual(views["engine"],"save_system")
        self.assertFalse(views["training_candidate_mutated"])

    def test_invalid_mirror_worker_controls_fail_before_threads(self):
        source=make_studio_source("economy")
        for bad in (
            {"angles":["explore","explore"]},
            {"angles":["python-execute"]},
            {"steps":49},
            {"workers":5},
            {"seed":2**31},
            {"angles":[]},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ScenarioLabError):
                    mirrored_simulations(source,**bad)

    def test_sales_evidence_never_declares_quality_or_game_asset_rights(self):
        source=sales_informed_catalog()
        self.assertEqual(len(source["entries"]),len(MOTIFS))
        for entry in source["entries"]:
            self.assertIn(entry["chart"],CHARTS)
            self.assertIn(entry["editor"],ENGINES)
            self.assertTrue("Original" in entry["motif"] or "Independent" in entry["motif"])
            self.assertGreater(entry["rank"],0)
        self.assertEqual(source["evidence_use"],"prioritize_questions_not_copy_content_or_certify_design_quality")
        filtered=sales_informed_catalog("racing")
        self.assertTrue(filtered["entries"])
        self.assertTrue(all(row["editor"]=="racing" for row in filtered["entries"]))
        with self.assertRaises(ScenarioLabError):
            sales_informed_catalog("made_up_runtime")

    def test_gleaned_source_bound_scenario_drafts_are_not_self_approved(self):
        source=make_studio_source("economy",{"market_nodes":3,"goods":10})
        observed=[{"mean_return":-3.5,"failure_rate":0.5,"episodes":5}]
        report=propose_scenarios(source,observations=observed,limit=4)
        self.assertEqual(report["engine"],"economy")
        self.assertEqual(report["measured_episode_count"],5)
        self.assertFalse(report["automatic_training_performed"])
        self.assertFalse(report["scenarios_verified_as_successful"])
        self.assertTrue(report["requires_rights_and_operator_training_admission"])
        self.assertTrue(report["scenarios"])
        for entry in report["scenarios"]:
            patched=apply_rule_proposal(source,entry["proposal"])
            self.assertNotEqual(patched,source)
            self.assertEqual(patched["editor"],source["editor"])
            self.assertEqual(patched["actions"],source["actions"])
            self.assertEqual(len(entry["variant_source_digest"]),64)
            self.assertFalse(entry["sales_rank_is_quality_evidence"])

    def test_observation_injection_cannot_author_or_modify_game_source(self):
        source=make_studio_source("economy")
        with self.assertRaises(ScenarioLabError):
            propose_scenarios(source,observations=[{
                "mean_return":float("nan"),"failure_rate":0.0,"episodes":1,
            }])
        with self.assertRaises(ScenarioLabError):
            propose_scenarios(source,observations=[{
                "mean_return":1,"failure_rate":0,"episodes":5,
                "command":"exec('malware')",
            }])


if __name__=="__main__":
    unittest.main()
