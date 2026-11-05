"""pressure_recovery: eight source stages, no real device or authorization claim."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.pressure_recovery.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestAdmission(unittest.TestCase):
    def test_complete_synthetic_evidence_still_cannot_authorize_native(self):
        record = evaluate_domain("pressure_recovery", successful_evidence(STAGE_TYPES))
        self.assertEqual(tuple(x.stage for x in record.stages), STAGES)
        self.assertTrue(record.accepted)
        self.assertFalse(record.to_record()["native_inference_witnessed"])
        self.assertFalse(record.to_record()["physical_device_qualified"])
        self.assertFalse(record.to_record()["release_certified"])

    def test_each_independent_denial_holds_full_contract(self):
        for label, case in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=label):
                verdict = evaluate_domain("pressure_recovery", case)
                self.assertFalse(verdict.accepted)
                self.assertEqual(
                    [x.stage for x in verdict.stages if not x.accepted],
                    [label],
                )

    def test_all_stage_names_have_exact_contracts(self):
        self.assertEqual(tuple(x["stage"] for x in contracts()), STAGES)
        self.assertEqual(len(contracts()), 8)
