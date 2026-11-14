"""CPU-only, explicit-approval and completion-only native SFT policy contracts."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.policy import SupervisedPolicy
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


def approved(**kwargs):
    return SupervisedPolicy(operator_approved=True,**kwargs)


class TestNativeSupervisedPolicy(unittest.TestCase):
    def test_approval_is_required(self):
        with self.assertRaises(SupervisedRejected):
            SupervisedPolicy()

    def test_original_candidate_only(self):
        p=approved()
        self.assertEqual(p.device,"cpu")
        self.assertEqual(p.loss_scope,"completion_only")
        self.assertTrue(p.candidate_only)
        self.assertEqual(p.source_license,"skeleton_original")
        self.assertEqual(p.training_scope,"offline_native_candidate_training")

    def test_canonical_full_round_trip(self):
        p=approved()
        self.assertEqual(SupervisedPolicy.parse(p.record()),p)
        self.assertEqual(len(p.sha256),64)

    def test_unknown_policy_field_fails_closed(self):
        row=approved().record()
        row["production_model"]=True
        with self.assertRaises(SupervisedRejected):
            SupervisedPolicy.parse(row)

    def test_no_prompt_training(self):
        with self.assertRaises(SupervisedRejected):
            replace(approved(),loss_scope="prompt_and_completion")

    def test_no_live_promotion(self):
        with self.assertRaises(SupervisedRejected):
            replace(approved(),candidate_only=False)

    def test_no_gpu_silent_fallback(self):
        for device in ("cuda","gpu","auto","torch","mps"):
            with self.subTest(device=device),self.assertRaises(SupervisedRejected):
                replace(approved(),device=device)

    def test_incompatible_head_geometry(self):
        with self.assertRaises(SupervisedRejected):
            replace(approved(),heads=3,dimension=16)

    def test_int_bools_are_forbidden(self):
        for name in ("seed","dimension","context","epochs","max_optimizer_steps"):
            with self.subTest(name=name),self.assertRaises(SupervisedRejected):
                replace(approved(),**{name:True})

    def test_budget_bounds(self):
        for name,value in (("epochs",0),("batch_examples",0),
                           ("max_optimizer_steps",1000001),
                           ("learning_rate_ppm",100001),
                           ("max_checkpoint_bytes",256000001)):
            with self.subTest(name=name),self.assertRaises(SupervisedRejected):
                replace(approved(),**{name:value})


if __name__=="__main__":
    unittest.main()
