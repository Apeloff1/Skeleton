"""signed_sources: reject malformed, incomplete and type-confused source evidence."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence, mutation_cases
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.signed_sources.registry import STAGES, STAGE_TYPES, contracts

class TestHostile(unittest.TestCase):
    def test_all_stage_names_required_exactly(self):
        valid = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(missing=stage):
                partial = dict(valid)
                del partial[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("signed_sources", partial)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("signed_sources", {**valid, "untrusted_override": True})

    def test_wrong_type_and_injected_fields_rejected(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                value = successful_evidence(STAGE_TYPES)
                key = next(iter(value[stage]))
                value[stage][key] = [] if kind in ("sha_equal","same_owner") else "true"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("signed_sources", value)
                value = successful_evidence(STAGE_TYPES)
                value[stage]["override"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("signed_sources", value)

    def test_non_mapping_cannot_become_authority(self):
        for item in (None, (), [], "", 0, True):
            with self.assertRaises(LaptopGateHold):
                evaluate_domain("signed_sources", item)
