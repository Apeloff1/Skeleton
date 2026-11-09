"""cold_restart: each of eight source stages must produce a typed verdict."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.cold_restart.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestAdmission(unittest.TestCase):
    def test_all_stages_present_in_order_with_non_authority_holds(self):
        verdict = evaluate_domain("cold_restart", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertEqual(tuple(v.stage for v in verdict.stages), STAGES)
        self.assertFalse(verdict.to_record()["native_inference_witnessed"])
        self.assertFalse(verdict.to_record()["physical_device_qualified"])
        self.assertFalse(verdict.to_record()["release_certified"])

    def test_each_invalid_stage_denies_without_faking_recovery(self):
        for stage, fixture in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                report = evaluate_domain("cold_restart", fixture)
                self.assertFalse(report.accepted)
                self.assertEqual([v.stage for v in report.stages if not v.accepted],[stage])

    def test_declared_contracts_match_exact_stage_inventory(self):
        self.assertEqual(tuple(v["stage"] for v in contracts()), STAGES)
