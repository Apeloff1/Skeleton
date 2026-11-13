"""Malformed release claims do not override real security/release holds."""
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

class TestReleaseHostile(unittest.TestCase):
    def test_missing_release_stage_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(source); del partial[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("release_gates", partial)

    def test_unknown_fields_and_nonmapping_values_rejected(self):
        original = successful_evidence(STAGE_TYPES)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("release_gates", {**original,"release_override":True})
        for value in (None,[],(),True,0,"ready"):
            with self.assertRaises(LaptopGateHold):
                evaluate_domain("release_gates", value)

    def test_each_stages_scalar_type_must_be_exact(self):
        for stage,kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                payload = successful_evidence(STAGE_TYPES)
                first = next(iter(payload[stage]))
                payload[stage][first] = [] if kind in ("sha_equal","same_owner") else "true"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("release_gates", payload)

    def test_extra_internal_claim_is_rejected(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                payload = successful_evidence(STAGE_TYPES)
                payload[stage]["release_certified"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("release_gates", payload)
