"""Full all-domain diagnostics still cannot certify an actual running GGUF."""
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

from skeleton.jeeves.native_fabric.laptop_ops.batch.records import HOLDS

class TestWholeLaptopSourceAdmission(unittest.TestCase):
    def test_all_20_x_8_complete_source_diagnostics(self):
        value = evaluate_bundle(successful_bundle())
        record = value.to_record()
        self.assertTrue(value.accepted_source_only)
        self.assertTrue(record["accepted_source_only"])
        self.assertEqual(record["schema"], "jeeves.laptop_ops.bundle.v1")
        self.assertEqual(record["domain_count"], 20)
        self.assertEqual(record["stage_count"], 160)
        self.assertEqual(tuple(row["domain"] for row in record["domains"]), list_domains())
        self.assertEqual(len(record["domains"]), 20)
        self.assertEqual(sum(len(x["stages"]) for x in record["domains"]), 160)
        self.assertEqual(record["holds"], list(HOLDS))

    def test_source_acceptance_is_not_activation_or_release(self):
        report = evaluate_bundle(successful_bundle()).to_record()
        self.assertIs(report["operator_claims_are_not_authority"], True)
        self.assertIs(report["real_native_inference_witnessed"], False)
        self.assertIs(report["physical_device_qualified"], False)
        self.assertIs(report["release_certified"], False)
        self.assertTrue(report["holds"])
        for domain in report["domains"]:
            with self.subTest(domain=domain["domain"]):
                self.assertIs(domain["native_inference_witnessed"], False)
                self.assertIs(domain["physical_device_qualified"], False)
                self.assertIs(domain["release_certified"], False)

    def test_strict_json_round_trip_preserves_canonical_receipt(self):
        source = successful_bundle()
        expected = evaluate_bundle(source)
        actual = evaluate_json(encode_bundle(source))
        self.assertEqual(expected.to_record(), actual.to_record())
        self.assertEqual(expected.evidence_sha256, actual.evidence_sha256)
        self.assertEqual(expected.manifest_sha256, manifest()["manifest_sha256"])

    def test_record_contains_fingerprints_not_private_input_text(self):
        record = evaluate_bundle(successful_bundle()).to_record()
        self.assertEqual(len(record["manifest_sha256"]), 64)
        self.assertEqual(len(record["evidence_sha256"]), 64)
        self.assertNotIn("private_path", record)
        self.assertNotIn("operator_task", record)
        self.assertNotIn("raw_model_bytes", record)
