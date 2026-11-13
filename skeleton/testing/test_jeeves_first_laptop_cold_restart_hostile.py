"""cold_restart: refuse malformed or incomplete operator evidence."""
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

class TestHostile(unittest.TestCase):
    def test_missing_and_extra_stages_deny(self):
        source = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(source); del partial[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cold_restart", partial)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("cold_restart", {**source,"override":True})

    def test_nonmapping_and_untyped_payloads_deny(self):
        for value in (None, [], (), "", True, 99):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cold_restart", value)
        for stage,kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                e = successful_evidence(STAGE_TYPES)
                k = next(iter(e[stage]))
                e[stage][k] = [] if kind in ("sha_equal","same_owner") else "2"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cold_restart", e)

    def test_unknown_nested_evidence_field_rejected(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                e = successful_evidence(STAGE_TYPES)
                e[stage]["unexpected"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("cold_restart", e)
