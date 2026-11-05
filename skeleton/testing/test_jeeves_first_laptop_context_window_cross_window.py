"""Valid individual quotas can still exceed total real model context."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.context_window.registry import STAGES, STAGE_TYPES, contracts

class TestContextCrossWindow(unittest.TestCase):
    def test_total_prompt_plus_output_must_fit_model(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["output_reservation"]["reserved"] = 4095
        # Each stage passes independently: reserved <= observed capacity 4096.
        # But 2 prompt tokens plus 4095 output tokens exceed 4096.
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("context_window", evidence)

    def test_equal_context_boundary_is_admissible_diagnostic_only(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["output_reservation"]["reserved"] = 4094
        result = evaluate_domain("context_window", evidence)
        self.assertTrue(result.accepted)
        self.assertFalse(result.to_record()["physical_device_qualified"])

    def test_changing_role_digest_cannot_authorize_overflow(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["output_reservation"]["reserved"] = 4095
        evidence["role_integrity"]["observed_sha256"] = "b" * 64
        report = evaluate_domain("context_window", evidence)
        self.assertFalse(report.accepted)
