"""CPU queue + active worker reservations must fit same host capacity."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.cpu_admission.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestCpuCoherence(unittest.TestCase):
    def test_individually_valid_quotas_may_exceed_combined_capacity(self):
        source = successful_evidence(STAGE_TYPES)
        source["thread_capacity"]["reserved"] = 4096
        # This independent queue stage has 512 reserved, also individually valid.
        with self.assertRaisesRegex(LaptopGateHold, "oversubscribe"):
            evaluate_domain("cpu_admission", source)

    def test_exact_combined_boundary_is_observed_not_attested(self):
        source = successful_evidence(STAGE_TYPES)
        source["thread_capacity"]["reserved"] = 3584
        report = evaluate_domain("cpu_admission", source)
        self.assertTrue(report.accepted)
        self.assertFalse(report.to_record()["physical_device_qualified"])

    def test_negative_stage_does_not_hide_its_denial(self):
        stage, case = mutation_cases(STAGE_TYPES)[0]
        report = evaluate_domain("cpu_admission", case)
        self.assertFalse(report.accepted)
        self.assertIn(stage, [r.stage for r in report.stages if not r.accepted])

    def test_never_treat_boolean_as_an_available_core_count(self):
        source = successful_evidence(STAGE_TYPES)
        source["thread_capacity"]["available"] = True
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("cpu_admission", source)
