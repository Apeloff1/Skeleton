"""source_retrieval: full source-only admission and eight negative stage cases."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.source_retrieval.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class AdmissionTests(unittest.TestCase):
    def test_complete_diagnostic_is_not_an_installer_attestation(self):
        result = evaluate_domain("source_retrieval", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertEqual(tuple(v.stage for v in result.stages), STAGES)
        self.assertEqual(len(result.stages), 8)
        self.assertFalse(result.to_record()["native_inference_witnessed"])
        self.assertFalse(result.to_record()["physical_device_qualified"])
        self.assertFalse(result.to_record()["release_certified"])

    def test_every_denied_stage_holds_the_entire_domain(self):
        for name, sample in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=name):
                result = evaluate_domain("source_retrieval", sample)
                self.assertFalse(result.accepted)
                self.assertEqual([s.stage for s in result.stages if not s.accepted], [name])

    def test_complete_stage_inventory_is_deterministic(self):
        result = evaluate_domain("source_retrieval", successful_evidence(STAGE_TYPES))
        self.assertEqual(tuple(s.stage for s in result.stages), STAGES)
        self.assertEqual(len(contracts()), len(STAGES))
