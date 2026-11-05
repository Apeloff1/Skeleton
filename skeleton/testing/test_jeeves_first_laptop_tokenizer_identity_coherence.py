"""Independently matching but cross-model tokenizer hashes still deny."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.tokenizer_identity.registry import STAGES, STAGE_TYPES, contracts

class TokenizerCoherence(unittest.TestCase):
    def test_stages_consistent_in_independent_samples(self):
        source = successful_evidence(STAGE_TYPES)
        self.assertTrue(evaluate_domain("tokenizer_identity", source).accepted)

    def test_two_individually_equal_digests_must_match_each_other(self):
        source = successful_evidence(STAGE_TYPES)
        source["model_pairing"] = {
            "expected_sha256": "b" * 64, "observed_sha256": "b" * 64,
        }
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("tokenizer_identity", source)

    def test_unknown_module_cannot_be_authorized_by_source(self):
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("unknown_tokenizer", {})
