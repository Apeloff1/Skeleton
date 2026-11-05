"""Source-only bootstrap replay regression; not hardware qualification."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.bootstrap.registry import (
    STAGES, STAGE_TYPES, evaluate, contracts,
)


class TestBootstrapReplay(unittest.TestCase):

    def test_replay_stable_receipts(self):
        fixture = successful_evidence(STAGE_TYPES)
        first = evaluate_domain("bootstrap", fixture).to_record()
        second = evaluate_domain("bootstrap", fixture).to_record()
        self.assertEqual(first, second)
        self.assertEqual(len(first["evidence_sha256"]), 64)
        self.assertEqual(len({x["stage"] for x in first["stages"]}), 8)

    def test_mutation_changes_evidence_digest(self):
        fixture = successful_evidence(STAGE_TYPES)
        baseline = evaluate_domain("bootstrap", fixture).evidence_sha256
        mutated = mutation_cases(STAGE_TYPES)[0][1]
        changed = evaluate_domain("bootstrap", mutated)
        self.assertNotEqual(baseline, changed.evidence_sha256)

    def test_operator_fixture_does_not_assert_physical_native(self):
        fixture = successful_evidence(STAGE_TYPES)
        record = evaluate_domain("bootstrap", fixture).to_record()
        self.assertTrue(record["operator_claims_are_not_authority"])
        self.assertFalse(record["native_inference_witnessed"])
        self.assertFalse(record["physical_device_qualified"])
        self.assertFalse(record["release_certified"])

if __name__ == "__main__":
    unittest.main()
