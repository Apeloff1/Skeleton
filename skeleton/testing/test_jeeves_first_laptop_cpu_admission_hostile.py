"""CPU stage shape attacks cannot bypass independent predicates."""
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

class TestCpuHostile(unittest.TestCase):
    def test_every_missing_stage_is_rejected(self):
        baseline = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(baseline)
                del partial[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cpu_admission", partial)

    def test_unknown_stage_and_nonmapping_values(self):
        source = successful_evidence(STAGE_TYPES)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("cpu_admission", {**source, "bypass": True})
        for val in (None, [], (), "", True, 3):
            with self.subTest(type=type(val).__name__):
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cpu_admission", val)

    def test_stage_type_confusion_never_coerces_into_cpu_budget(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                forged = successful_evidence(STAGE_TYPES)
                field = next(iter(forged[stage]))
                forged[stage][field] = [] if kind == "same_owner" else "1"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cpu_admission", forged)

    def test_extra_nested_field_is_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                case = {k: dict(v) for k,v in source.items()}
                case[stage]["override"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cpu_admission", case)
