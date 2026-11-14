"""Native model genesis policy validates every costly and privileged dimension."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


def valid_policy():
    return GenesisPolicy(operator_approved=True)


class TestNativeGenesisPolicy(unittest.TestCase):
    def test_operator_must_explicitly_approve(self):
        with self.assertRaises(GenesisRejected):
            GenesisPolicy()

    def test_source_only_cpu_policy(self):
        policy=valid_policy()
        self.assertEqual(policy.device,"cpu")
        self.assertEqual(policy.training_scope,"offline_native_candidate_training")
        self.assertEqual(policy.license_id,"skeleton_original")
        self.assertTrue(policy.candidate_only)
        self.assertEqual(len(policy.digest),64)

    def test_roundtrip_fields_and_digest(self):
        policy=valid_policy()
        self.assertEqual(GenesisPolicy.from_record(policy.record()),policy)
        self.assertEqual(GenesisPolicy.from_record(policy.record()).digest,policy.digest)

    def test_unknown_field_denied(self):
        raw=valid_policy().record()
        raw["remote_provider"]="llm_fallback"
        with self.assertRaises(GenesisRejected):
            GenesisPolicy.from_record(raw)

    def test_production_deployment_denied(self):
        with self.assertRaises(GenesisRejected):
            replace(valid_policy(),candidate_only=False)

    def test_gpu_device_denied_without_fallback(self):
        for device in ("cuda","gpu","mps","auto","torch"):
            with self.subTest(device=device),self.assertRaises(GenesisRejected):
                replace(valid_policy(),device=device)

    def test_incompatible_attention_head_denied(self):
        with self.assertRaises(GenesisRejected):
            replace(valid_policy(),dim=16,n_heads=3)

    def test_bool_is_not_valid_budget(self):
        for key in ("seed","dim","ctx","n_heads","max_vocab",
                    "maximum_model_bytes","max_optimizer_steps"):
            with self.subTest(field=key),self.assertRaises(GenesisRejected):
                replace(valid_policy(),**{key:True})

    def test_identity_changes_digest(self):
        self.assertNotEqual(valid_policy().digest,replace(valid_policy(),seed=43).digest)

    def test_candidate_training_plan_not_self_promotion(self):
        plan=valid_policy().for_candidate_training("a"*64,"b"*64)
        self.assertTrue(plan.operator_approved)
        self.assertEqual(plan.output_kind,"candidate-only")
        self.assertEqual(plan.max_optimizer_steps,32000)


if __name__=="__main__":
    unittest.main()
