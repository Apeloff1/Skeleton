"""Malformed or forged memory capacity evidence must fail closed."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.memory_capacity.registry import STAGES, STAGE_TYPES, contracts

class TestMemoryHostile(unittest.TestCase):
    def test_missing_and_extra_stages(self):
        baseline = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                missing = dict(baseline); del missing[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("memory_capacity", missing)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("memory_capacity", {**baseline, "override": True})

    def test_type_confusion_and_extra_fields(self):
        for stage, _ in STAGE_TYPES:
            with self.subTest(stage=stage):
                source = successful_evidence(STAGE_TYPES)
                first = next(iter(source[stage]))
                source[stage][first] = "1000"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("memory_capacity", source)
                source = successful_evidence(STAGE_TYPES)
                source[stage]["override"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("memory_capacity", source)
