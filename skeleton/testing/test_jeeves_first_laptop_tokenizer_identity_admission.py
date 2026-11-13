"""Tokenization diagnostic admission, bounded and non-authoritative."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.tokenizer_identity.registry import STAGES, STAGE_TYPES, contracts

class TokenizerAdmission(unittest.TestCase):
    def test_complete_source_inventory(self):
        v = evaluate_domain("tokenizer_identity", successful_evidence(STAGE_TYPES))
        self.assertTrue(v.accepted)
        self.assertEqual(len(v.stages), 8)
        self.assertEqual(tuple(row.stage for row in v.stages), STAGES)
        self.assertFalse(v.to_record()["native_inference_witnessed"])
        self.assertFalse(v.to_record()["release_certified"])

    def test_each_stage_failure_denies(self):
        for stage, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                v = evaluate_domain("tokenizer_identity", sample)
                self.assertFalse(v.accepted)
