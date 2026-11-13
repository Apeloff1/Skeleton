"""Source-only bootstrap hostile regression; not hardware qualification."""
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


class TestBootstrapHostile(unittest.TestCase):

    def test_missing_stage_holds(self):
        fixture = successful_evidence(STAGE_TYPES)
        for name in STAGES:
            with self.subTest(stage=name):
                bad = dict(fixture)
                bad.pop(name)
                with self.assertRaises(LaptopGateHold):
                    evaluate(bad)

    def test_unapproved_extra_stage_holds(self):
        fixture = successful_evidence(STAGE_TYPES)
        fixture["untrusted_override"] = {"verified": True}
        with self.assertRaises(LaptopGateHold):
            evaluate(fixture)

    def test_type_confusion_fails_closed(self):
        fixture = successful_evidence(STAGE_TYPES)
        for stage in STAGES:
            with self.subTest(stage=stage):
                bad = {k: dict(v) for k,v in fixture.items()}
                key = next(iter(bad[stage]))
                bad[stage][key] = object()
                with self.assertRaises(LaptopGateHold):
                    evaluate(bad)

    def test_list_is_not_a_typed_stage_mapping(self):
        with self.assertRaises(LaptopGateHold):
            evaluate([])

if __name__ == "__main__":
    unittest.main()
