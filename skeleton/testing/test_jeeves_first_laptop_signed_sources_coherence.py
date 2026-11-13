"""signed_sources: reject cross-stage inconsistent but individually passing facts."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.signed_sources.registry import STAGES, STAGE_TYPES, contracts

class TestCoherence(unittest.TestCase):
    def test_consistent_synthetic_evidence_is_not_activation(self):
        result = evaluate_domain("signed_sources", successful_evidence(STAGE_TYPES))
        self.assertTrue(result.accepted)
        self.assertFalse(result.to_record()["release_certified"])

    def test_synthetic_stage_agreement_is_not_sufficient(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["loaded_manifest"] = {"expected_sha256": "b"*64, "observed_sha256": "b"*64}
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("signed_sources", evidence)

    def test_one_missing_stage_always_denies(self):
        evidence = successful_evidence(STAGE_TYPES)
        del evidence[STAGES[-1]]
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("signed_sources", evidence)
