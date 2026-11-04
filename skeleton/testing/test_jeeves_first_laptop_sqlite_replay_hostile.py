"""sqlite_replay: fail closed for partial, forged and ill-typed source evidence."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.sqlite_replay.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class HostileTests(unittest.TestCase):
    def test_every_missing_stage_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        for label in STAGES:
            with self.subTest(missing=label):
                truncated = dict(source)
                truncated.pop(label)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("sqlite_replay", truncated)

    def test_unknown_stages_and_nonmappings_rejected(self):
        source = successful_evidence(STAGE_TYPES)
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("sqlite_replay", {**source, "extra": True})
        for value in (None, True, [], (), 3, ""):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("sqlite_replay", value)

    def test_wrong_scalar_type_in_every_stage(self):
        for label, kind in STAGE_TYPES:
            with self.subTest(stage=label):
                case = successful_evidence(STAGE_TYPES)
                first = next(iter(case[label]))
                case[label][first] = [] if kind in ("sha_equal","same_owner") else "1"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("sqlite_replay", case)

    def test_no_nested_unknown_field_is_ignored(self):
        for label in STAGES:
            with self.subTest(stage=label):
                case = successful_evidence(STAGE_TYPES)
                case[label]["authorization_override"] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("sqlite_replay", case)
