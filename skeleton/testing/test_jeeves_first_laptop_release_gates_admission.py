"""Release source diagnostics never establish an independent release pass."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.release_gates.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestReleaseAdmission(unittest.TestCase):
    def test_all_eight_stage_contracts_are_explicit(self):
        result = evaluate_domain("release_gates", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertEqual(tuple(item.stage for item in result.stages), STAGES)
        self.assertFalse(result.to_record()["native_inference_witnessed"])
        self.assertFalse(result.to_record()["physical_device_qualified"])
        self.assertFalse(result.to_record()["release_certified"])
        self.assertTrue(result.to_record()["operator_claims_are_not_authority"])

    def test_no_individual_release_gate_can_be_omitted_or_failed(self):
        for label,evidence in mutation_cases(STAGE_TYPES):
            with self.subTest(label=label):
                verdict = evaluate_domain("release_gates", evidence)
                self.assertFalse(verdict.accepted)
                self.assertEqual([v.stage for v in verdict.stages if not v.accepted], [label])

    def test_source_fixture_is_not_ci_evidence(self):
        doc = evaluate_domain("release_gates", successful_evidence(STAGE_TYPES)).to_record()
        self.assertNotIn("github_ci_success", doc)
        self.assertNotIn("gguf_device_verified", doc)
        self.assertFalse(doc["release_certified"])
