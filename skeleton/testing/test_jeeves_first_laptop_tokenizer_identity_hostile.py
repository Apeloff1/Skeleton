"""Tokenization diagnostics reject type-coerced or missing source data."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.tokenizer_identity.registry import STAGES, STAGE_TYPES, contracts

class TokenizerHostile(unittest.TestCase):
    def test_missing_and_extra_source_stages(self):
        baseline = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                missing = dict(baseline)
                missing.pop(stage)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("tokenizer_identity", missing)
        extra = dict(baseline); extra["license_override"] = True
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("tokenizer_identity", extra)

    def test_refuse_type_confusion_and_unexpected_field(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                evidence = successful_evidence(STAGE_TYPES)
                first = next(iter(evidence[stage]))
                evidence[stage][first] = [] if kind in ("sha_equal", "same_owner") else "true"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("tokenizer_identity", evidence)
                evidence = successful_evidence(STAGE_TYPES)
                evidence[stage]["extra"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("tokenizer_identity", evidence)
