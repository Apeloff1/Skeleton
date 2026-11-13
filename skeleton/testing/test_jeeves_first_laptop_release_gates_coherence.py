"""Source-only release digest pairs must agree before any positive diagnostic."""
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

class TestReleaseCoherence(unittest.TestCase):
    def test_two_individually_valid_but_different_models_refused(self):
        evidence = successful_evidence(STAGE_TYPES)
        evidence["installed_model"] = {
            "expected_sha256": "b" * 64,
            "observed_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(LaptopGateHold, "do not match"):
            evaluate_domain("release_gates", evidence)

    def test_consistent_source_only_case_does_not_certify_release(self):
        observed = evaluate_domain("release_gates", successful_evidence(STAGE_TYPES))
        self.assertTrue(observed.accepted)
        self.assertFalse(observed.to_record()["release_certified"])

    def test_one_failed_gate_retains_explicit_verdict(self):
        label,case = mutation_cases(STAGE_TYPES)[0]
        record = evaluate_domain("release_gates",case)
        self.assertFalse(record.accepted)
        self.assertIn(label,[v.stage for v in record.stages if not v.accepted])
