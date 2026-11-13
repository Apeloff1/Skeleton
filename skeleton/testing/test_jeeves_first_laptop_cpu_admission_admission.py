"""Eight CPU safeguards; source fixtures are not physical evidence."""
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

class TestCpuAdmission(unittest.TestCase):
    def test_complete_source_fixture_does_not_activate_gguf(self):
        verdict = evaluate_domain("cpu_admission", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertEqual(tuple(s.stage for s in verdict.stages), STAGES)
        self.assertEqual(len(verdict.stages), 8)
        self.assertFalse(verdict.to_record()["native_inference_witnessed"])
        self.assertFalse(verdict.to_record()["physical_device_qualified"])
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_every_negative_stage_blocks_aggregate(self):
        for stage, mutated in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                verdict = evaluate_domain("cpu_admission", mutated)
                self.assertFalse(verdict.accepted)
                self.assertEqual(
                    [row.stage for row in verdict.stages if not row.accepted],
                    [stage],
                )

    def test_reserved_slots_do_not_authorize_extra_threads(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["thread_capacity"]["reserved"] = 2048
        evidence["queue_admission"]["reserved"] = 2048
        result = evaluate_domain("cpu_admission", evidence)
        self.assertTrue(result.accepted)
        self.assertFalse(result.to_record()["physical_device_qualified"])
