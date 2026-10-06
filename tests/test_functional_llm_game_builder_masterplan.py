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

        readme=(ROOT/"docs/plan/FUNCTIONAL_LLM_GAME_BUILDER_10MB/README.md").read_text(encoding="utf-8")
        self.assertIn(f"{target:,}",readme)
        self.assertIn(f"{total:,}",readme)

if __name__=="__main__":
    unittest.main()
