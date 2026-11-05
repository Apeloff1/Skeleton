"""Determinism and integrity of model_manifest source-only replay."""
from __future__ import annotations
import copy
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import successful_evidence
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.model_manifest.registry import STAGE_TYPES

class TestModelManifestReplay(unittest.TestCase):
    def test_reordering_and_repeat_are_identical(self):
        source = successful_evidence(STAGE_TYPES)
        first = evaluate_domain("model_manifest", source).to_record()
        reordered = dict(reversed(list(source.items())))
        self.assertEqual(first, evaluate_domain("model_manifest", reordered).to_record())
        self.assertEqual(first, evaluate_domain("model_manifest", copy.deepcopy(source)).to_record())

    def test_one_changed_hash_changes_receipt(self):
        source = successful_evidence(STAGE_TYPES)
        before = evaluate_domain("model_manifest", source)
        source["installed_model_digest"]["observed_sha256"] = "b" * 64
        after = evaluate_domain("model_manifest", source)
        self.assertNotEqual(before.evidence_sha256, after.evidence_sha256)
        self.assertFalse(after.accepted)

if __name__ == "__main__":
    unittest.main()
