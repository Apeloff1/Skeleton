"""Reject malformed and hostile model_manifest operator evidence."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.model_manifest.registry import STAGES, STAGE_TYPES

class TestModelManifestHostile(unittest.TestCase):
    def test_missing_and_extra_fields(self):
        base = successful_evidence(STAGE_TYPES)
        for label in STAGES:
            with self.subTest(label=label):
                missing = dict(base); missing.pop(label)
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("model_manifest", missing)
        extra = dict(base); extra["unknown_safeguard"] = {}
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("model_manifest", extra)

    def test_wrong_type_is_not_a_denial_result(self):
        for stage, kind in STAGE_TYPES:
            with self.subTest(stage=stage):
                broken = successful_evidence(STAGE_TYPES)
                key = next(iter(broken[stage]))
                broken[stage][key] = [] if kind in ("sha_equal", "same_owner") else "true"
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("model_manifest", broken)

    def test_top_level_must_be_exact_dictionary(self):
        for candidate in (None, [], (), "approved", True, 1):
            with self.subTest(candidate=str(type(candidate))):
                with self.assertRaises(LaptopGateHold):
                    evaluate_domain("model_manifest", candidate)

if __name__ == "__main__":
    unittest.main()
