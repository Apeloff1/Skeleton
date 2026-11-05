"""pressure_recovery: adversarial field and scalar type confusion is held."""
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

class TestHostile(unittest.TestCase):
    def test_every_missing_stage_is_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(source); partial.pop(stage)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("pressure_recovery", partial)

    def test_extra_stages_and_nonmapping_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("pressure_recovery", {**source, "override": True})
        for value in (None, True, [], (), 2, ""):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("pressure_recovery", value)

    def test_no_type_coercion_and_no_hidden_fields(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                value = successful_evidence(STAGE_TYPES)
                field = next(iter(value[stage]))
                value[stage][field] = [] if kind in ("same_owner","sha_equal") else "1"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("pressure_recovery", value)
                value = successful_evidence(STAGE_TYPES)
                value[stage]["operator_override"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("pressure_recovery", value)
