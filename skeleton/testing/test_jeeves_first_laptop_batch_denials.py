"""Every independently failing stage across twenty domains denies the bundle."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.batch.catalog import manifest
from skeleton.jeeves.native_fabric.laptop_ops.batch.fixtures import (
    successful_bundle, negative_bundle, encode_bundle,
)
from skeleton.jeeves.native_fabric.laptop_ops.batch.runner import (
    evaluate_bundle, evaluate_json,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains

import importlib

class TestAll160NegativeMutations(unittest.TestCase):
    def test_160_single_stage_failures_never_count_as_source_acceptance(self):
        total = 0
        for domain in list_domains():
            module = importlib.import_module(
                "skeleton.jeeves.native_fabric.laptop_ops.domains."
                + domain + ".registry"
            )
            for stage in module.STAGES:
                with self.subTest(domain=domain, stage=stage):
                    modified = negative_bundle(domain, stage)
                    result = evaluate_bundle(modified)
                    self.assertFalse(result.accepted_source_only)
                    record = result.to_record()
                    self.assertFalse(record["accepted_source_only"])
                    self.assertFalse(record["real_native_inference_witnessed"])
                    self.assertFalse(record["release_certified"])
                    denial = next(x for x in record["domains"] if x["domain"] == domain)
                    self.assertFalse(denial["accepted"])
                    self.assertIn(
                        stage, [row["stage"] for row in denial["stages"]
                                if not row["accepted"]],
                    )
                    total += 1
        self.assertEqual(total, 160)

    def test_unknown_negative_fixture_stage_is_refused(self):
        with self.assertRaises(LaptopGateHold):
            negative_bundle("bootstrap", "not_a_stage")
        with self.assertRaises(LaptopGateHold):
            negative_bundle("never_registered", "unknown")

    def test_denial_fingerprint_differs_from_complete_source_case(self):
        baseline = evaluate_bundle(successful_bundle())
        for domain in list_domains():
            first_stage = next(iter(successful_bundle()[domain]))
            changed = evaluate_bundle(negative_bundle(domain, first_stage))
            with self.subTest(domain=domain):
                self.assertNotEqual(changed.evidence_sha256, baseline.evidence_sha256)
                self.assertFalse(changed.accepted_source_only)
