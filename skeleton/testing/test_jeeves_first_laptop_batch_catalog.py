"""Complete source roster: exactly twenty domains and 160 declared safeguards."""
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

from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
from skeleton.jeeves.native_fabric.laptop_ops.batch.limits import (
    BundleLimits, DEFAULT_BUNDLE_LIMITS, DOMAIN_COUNT, TOTAL_STAGES,
)

class TestCompleteSourceCatalog(unittest.TestCase):
    def test_exact_twenty_domains_and_eight_stages_each(self):
        entry = manifest()
        self.assertEqual(entry["schema"], "jeeves.laptop_ops.bundle_catalog.v1")
        self.assertEqual(len(entry["domains"]), DOMAIN_COUNT)
        self.assertEqual(DOMAIN_COUNT, 20)
        self.assertEqual(TOTAL_STAGES, 160)
        self.assertEqual(tuple(row["domain"] for row in entry["domains"]), list_domains())
        self.assertEqual(
            sum(len(row["stages"]) for row in entry["domains"]), TOTAL_STAGES
        )
        for domain in entry["domains"]:
            with self.subTest(domain=domain["domain"]):
                self.assertEqual(len(domain["stages"]), 8)
                self.assertEqual(
                    len({stage["name"] for stage in domain["stages"]}), 8
                )
                for stage in domain["stages"]:
                    self.assertEqual(
                        stage["required_fields"],
                        list(required_keys(stage["predicate"], stage["name"])),
                    )

    def test_source_manifest_fingerprint_is_stable(self):
        first = manifest()
        self.assertEqual(first, manifest())
        self.assertEqual(len(first["manifest_sha256"]), 64)
        self.assertEqual(first["native_inference_witnessed"], False)
        self.assertEqual(first["physical_device_qualified"], False)
        self.assertEqual(first["release_certified"], False)

    def test_bundle_limits_are_not_runtime_permissions(self):
        limits = DEFAULT_BUNDLE_LIMITS
        self.assertEqual(limits.domain_count, 20)
        self.assertEqual(limits.stage_count, 160)
        self.assertLessEqual(limits.max_evidence_bytes, 65536)
        self.assertLessEqual(limits.max_report_bytes, 131072)
        for changed in (
            {"domain_count": 21},
            {"stage_count": 159},
            {"max_evidence_bytes": 65537},
            {"max_report_bytes": 131073},
            {"domain_count": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(LaptopGateHold):
                    BundleLimits(**changed)
