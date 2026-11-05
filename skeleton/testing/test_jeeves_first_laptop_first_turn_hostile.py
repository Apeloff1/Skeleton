"""first_turn: fail closed on missing, unexpected or malformed evidence."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.first_turn.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestHostile(unittest.TestCase):
    def test_each_missing_source_stage_denies(self):
        source = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                partial = dict(source); del partial[stage]
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("first_turn", partial)

    def test_unrecognized_stages_and_nonmappings_fail(self):
        source = successful_evidence(STAGE_TYPES)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("first_turn", {**source, "override": True})
        for value in (None, [], (), 0, True, ""):
            with self.assertRaises(LaptopGateHold):
                evaluate_domain("first_turn", value)

    def test_wrong_scalar_types_and_nested_extra_fields_fail(self):
        for stage,kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                record = successful_evidence(STAGE_TYPES)
                key = next(iter(record[stage]))
                record[stage][key] = [] if kind in ("sha_equal","same_owner") else "1"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("first_turn", record)
                record = successful_evidence(STAGE_TYPES)
                record[stage]["bypass"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("first_turn", record)
