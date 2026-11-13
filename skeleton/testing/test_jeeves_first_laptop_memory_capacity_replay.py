"""Memory diagnostics must be independent of caller mapping order."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.memory_capacity.registry import STAGES, STAGE_TYPES, contracts

class TestMemoryReplay(unittest.TestCase):
    def test_stable_receipts(self):
        source = successful_evidence(STAGE_TYPES)
        original = evaluate_domain("memory_capacity", source).to_record()
        reordered = dict(reversed(tuple(source.items())))
        self.assertEqual(original, evaluate_domain("memory_capacity", reordered).to_record())

    def test_each_mutation_changes_exact_digest(self):
        original = evaluate_domain("memory_capacity", successful_evidence(STAGE_TYPES))
        for stage, fixture in mutation_cases(STAGE_TYPES):
            with self.subTest(stage=stage):
                updated = evaluate_domain("memory_capacity", fixture)
                self.assertNotEqual(original.evidence_sha256, updated.evidence_sha256)
                self.assertFalse(updated.accepted)
