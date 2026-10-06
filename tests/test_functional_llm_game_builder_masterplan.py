from __future__ import annotations
import json
import subprocess, sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FunctionalLLMGameBuilderMasterplanTest(unittest.TestCase):
    def test_validator_passes(self):
        proc=subprocess.run(
            [sys.executable,str(ROOT/"scripts/check_functional_llm_game_builder_10mb.py")],
            cwd=ROOT,text=True,capture_output=True,check=False,
        )
        self.assertEqual(proc.returncode,0,proc.stdout+"\n"+proc.stderr)
        self.assertIn("runtime completion remains unsigned",proc.stdout)

    def test_frontier_competition_contract_is_fail_closed_and_complete(self):
        data=json.loads((ROOT/"machine/functional_llm_game_builder_10mb_manifest.json").read_text(encoding="utf-8"))
        frontier=data["frontier_competition"]
        self.assertEqual(frontier["status"],"specification-registered-evidence-pending")
        self.assertFalse(frontier["completion_claim"])
        self.assertFalse(frontier["implementation_signed"])
        self.assertFalse(frontier["independent_verification_signed"])
        self.assertGreaterEqual(frontier["comparator_policy"]["minimum_frontier_comparators"],3)
        self.assertLessEqual(frontier["comparator_policy"]["maximum_comparator_age_days"],90)
        self.assertTrue(frontier["comparator_policy"]["strongest_available_comparator_required"])
        self.assertTrue(frontier["comparator_policy"]["contamination_controls_required"])
        self.assertEqual(
            [item["id"] for item in frontier["required_domains"]],
            [f"FC-{index:02d}" for index in range(1,13)],
        )
        self.assertGreaterEqual(sum(1 for item in frontier["required_domains"] if item["critical"]),9)
        rules=frontier["promotion_rules"]
        for key in (
            "no_critical_domain_may_be_hidden_by_aggregate_score",
            "safety_privacy_authority_rights_and_recovery_are_non_compensable",
            "game_builder_target_requires_frontier_parity_or_better",
            "long_horizon_consistency_target_requires_frontier_parity_or_better",
            "coding_repository_engineering_target_requires_frontier_parity_or_better",
            "dual_rival_gain_must_be_measured_against_single_pass_baseline",
            "exact_head_evidence_required",
            "independent_verification_required",
        ):
            self.assertTrue(rules[key])
        self.assertGreaterEqual(len(frontier["required_evidence"]),10)
        self.assertGreaterEqual(len(frontier["evaluation_modes"]),8)
        readme=(ROOT/"docs/plan/FUNCTIONAL_LLM_GAME_BUILDER_10MB/README.md").read_text(encoding="utf-8")
        self.assertIn("## Frontier competition finish line",readme)
        self.assertIn("at least three fresh frontier comparators",readme)
        self.assertIn("frontier parity or better",readme)

    def test_doubled_byte_ledger_and_pass2_contract(self):
        data=json.loads((ROOT/"machine/functional_llm_game_builder_10mb_manifest.json").read_text(encoding="utf-8"))
        byte_meta=data["bytes"]
        original=int(byte_meta["original_shard_total"])
        previous=int(byte_meta["previous_shard_total"])
        total=int(byte_meta["shard_total"])
        target=int(byte_meta["double_baseline_target"])
        self.assertEqual(previous,original)
        self.assertEqual(target,previous*2)
        self.assertGreaterEqual(int(byte_meta["requested_minimum"]),target)
        self.assertGreaterEqual(total,target)
        self.assertEqual(int(byte_meta["per_shard_minimum_total"]),int(byte_meta["per_shard_minimum"])*18)
        self.assertEqual(int(byte_meta["pass2_net_growth"]),total-previous)
        self.assertEqual(round(float(byte_meta["expansion_factor"]),4),round(total/previous,4))
        self.assertEqual(int(byte_meta["human_index_shard_total"]),total)
        self.assertEqual(int(byte_meta["expansion_generation"]),2)
        self.assertTrue(byte_meta["threshold_met"])
        self.assertTrue(byte_meta["doubled_target_met"])
        self.assertTrue(byte_meta["doubled_original_surface"])

        deep=data["deep_closure"]
        self.assertEqual(int(deep["required_atoms_per_plane"]),1296)
        self.assertEqual(int(deep["required_atoms_total"]),1296*18)
        expansion=data["deep_closure_expansion"]
        self.assertEqual(int(expansion["pass"]),2)
        self.assertEqual(expansion["status"],"registered-specification")
        self.assertEqual(int(expansion["per_plane_atoms"]),1296)
        self.assertEqual(int(expansion["total_atoms"]),1296*18)
        self.assertEqual(expansion["shape"]["planes"],18)
        self.assertEqual(expansion["shape"]["subsystems_per_plane"],12)
        self.assertEqual(expansion["shape"]["lifecycle_stages"],12)
        self.assertEqual(expansion["shape"]["adversarial_profiles"],9)
        self.assertEqual(data["coverage"]["deep_closure_adversarial_profiles"],deep["stress_profiles"])
        for shard in data["shards"]:
            self.assertTrue(shard["deep_closure_pass2_required"])
            self.assertEqual(int(shard["deep_closure_pass2_atoms"]),1296)
            self.assertEqual(int(shard["deep_closure_pass"]),2)
            self.assertFalse(shard["deep_closure_signed"])

        expected_legacy={
            "FLGB-01":259,"FLGB-02":258,"FLGB-03":259,"FLGB-04":260,
            "FLGB-05":259,"FLGB-06":293,"FLGB-07":294,"FLGB-08":293,
            "FLGB-09":295,"FLGB-10":292,"FLGB-11":295,"FLGB-12":294,
            "FLGB-13":295,"FLGB-14":293,"FLGB-15":295,"FLGB-16":277,
            "FLGB-17":278,"FLGB-18":276,
        }
        legacy=data["legacy_requirement_baseline"]
        self.assertEqual(
            legacy["source_commit"],
            "4f2d5f736bebc30e7156d0431da18ada41664afa",
        )
        self.assertEqual(legacy["per_plane"],expected_legacy)
        self.assertEqual(int(legacy["total_atoms"]),sum(expected_legacy.values()))
        for shard in data["shards"]:
            expected=expected_legacy[shard["id"]]
            self.assertEqual(int(shard["legacy_baseline_requirement_atoms"]),expected)
            self.assertEqual(int(shard["minimum_requirement_atoms"]),expected)

        readme=(ROOT/"docs/plan/FUNCTIONAL_LLM_GAME_BUILDER_10MB/README.md").read_text(encoding="utf-8")
        self.assertIn(f"{target:,}",readme)
        self.assertIn(f"{total:,}",readme)

if __name__=="__main__":
    unittest.main()
