"""Canonical all-domain receipt determinism and stable no-release holds."""
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

from copy import deepcopy
from skeleton.jeeves.native_fabric.laptop_ops.contracts import canonical, fingerprint

class TestBundleReplay(unittest.TestCase):
    def test_shuffling_domains_and_stages_does_not_change_record(self):
        original = successful_bundle()
        baseline = evaluate_bundle(original).to_record()
        shuffled = {
            domain: dict(reversed(tuple(value.items())))
            for domain, value in reversed(tuple(original.items()))
        }
        self.assertEqual(baseline, evaluate_bundle(shuffled).to_record())
        self.assertEqual(encode_bundle(original), encode_bundle(shuffled))

    def test_source_evidence_digest_changes_when_any_domain_is_mutated(self):
        baseline = evaluate_bundle(successful_bundle())
        for domain in list_domains():
            source = successful_bundle()
            stage = next(iter(source[domain]))
            changed = evaluate_bundle(negative_bundle(domain, stage))
            self.assertNotEqual(changed.evidence_sha256, baseline.evidence_sha256)

    def test_positive_and_negative_receipts_keep_release_holds(self):
        positive = evaluate_bundle(successful_bundle()).to_record()
        negative = evaluate_bundle(negative_bundle("bootstrap", "model_archive")).to_record()
        self.assertTrue(positive["accepted_source_only"])
        self.assertFalse(negative["accepted_source_only"])
        self.assertEqual(positive["holds"], negative["holds"])
        self.assertFalse(positive["release_certified"])
        self.assertFalse(negative["release_certified"])

    def test_invalid_object_cannot_override_fingerprints(self):
        source = successful_bundle()
        original = evaluate_bundle(source).to_record()
        clone = deepcopy(source)
        clone["bootstrap"]["model_archive"]["expected_sha256"] = "b" * 64
        mutated = evaluate_bundle(clone)
        self.assertNotEqual(mutated.evidence_sha256, original["evidence_sha256"])
        self.assertFalse(mutated.accepted_source_only)
