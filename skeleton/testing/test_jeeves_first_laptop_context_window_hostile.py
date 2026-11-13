"""Reject partial, overspecified and forged context observation stages."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.context_window.registry import STAGES, STAGE_TYPES, contracts

class TestContextHostile(unittest.TestCase):
    def test_missing_stages_and_unknown_override(self):
        baseline = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                missing = dict(baseline)
                missing.pop(stage)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("context_window", missing)
        baseline["model_context_override"] = True
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("context_window", baseline)

    def test_bool_count_and_string_count_are_not_valid_integer(self):
        for stage in ("model_context", "prompt_tokens", "output_reservation", "session_window"):
            for value in (True, "4096"):
                with self.subTest(stage=stage,value=value):
                    doc = successful_evidence(STAGE_TYPES)
                    key = "available" if stage in ("model_context", "output_reservation") else "used"
                    doc[stage][key] = value
                    with self.assertRaises(LaptopGateHold):
                        evaluate_domain("context_window", doc)

    def test_nonmapping_contract_is_not_acceptable(self):
        for candidate in (None, [], (), "ready", True):
            with self.assertRaises(LaptopGateHold):
                evaluate_domain("context_window", candidate)
