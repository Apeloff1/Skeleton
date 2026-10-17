"""SDK custody drift is comparison-only, not actual SDK/model training."""
from __future__ import annotations

import copy
import unittest

from skeleton.ai.training.sdk_custody_drift import (
    custody_snapshot, compare_custody,
)
from skeleton.ai.training.sdk_study import SDK_SCHEMA, SDKStudyError


def fixture(sha: str = "a" * 64, *, trainable: bool = True,
            version: str = "1.0", rights: str = "license:reviewed"):
    return {
        "sdk_id": "original_sdk", "document": "manual/intro.md",
        "version": version, "sdk_kind": "console",
        "target_ids": ("game_boy",), "trainable": trainable,
        "rights": {"rights_basis": rights, "human_reviewed": trainable,
                   "training_permitted": trainable},
    }


def build(sources):
    report = {
        "schema_version": SDK_SCHEMA,
        "manifest_sha256": "f" * 64,
        "pinned_documents": len(sources),
    }
    return custody_snapshot(report, sources)


class SDKCustodyDriftTests(unittest.TestCase):
    def test_identical_redacted_snapshots_do_not_retrain(self):
        source = {"a" * 64: fixture()}
        old = build(source)
        result = compare_custody(old, copy.deepcopy(old))
        self.assertEqual(result["unchanged_documents"], 1)
        self.assertEqual(result["changes"], [])
        self.assertFalse(result["production_jeeves_weights_updated"])

    def test_byte_revision_and_license_revocation_need_review(self):
        old = build({"a" * 64: fixture()})
        changed = build({"b" * 64: fixture(version="1.1")})
        delta = compare_custody(old, changed)
        self.assertEqual(delta["changes"][0]["change"],
                         "source_bytes_changed_require_review")
        revoked = build({"a" * 64: fixture(trainable=False)})
        self.assertEqual(compare_custody(old, revoked)["changes"][0]["change"],
                         "training_authority_revoked")

    def test_tampered_snapshot_and_duplicate_document_rejected(self):
        old = build({"a" * 64: fixture()})
        tampered = copy.deepcopy(old)
        tampered["documents"][0]["trainable"] = False
        with self.assertRaises(SDKStudyError):
            compare_custody(old, tampered)
        with self.assertRaises(SDKStudyError):
            build({"a" * 64: fixture(), "b" * 64: fixture()})

    def test_self_rehashed_malformed_record_still_fails_closed(self):
        from skeleton.ai.training.sdk_custody_drift import _digest
        old = build({"a" * 64: fixture()})
        for field, value in (
            ("trainable", "yes"),
            ("rights_review_digest", "not-a-sha"),
            ("target_ids", ["game_boy", "game_boy"]),
        ):
            forged = copy.deepcopy(old)
            forged["documents"][0][field] = value
            forged["snapshot_digest"] = _digest({
                key: value for key, value in forged.items()
                if key != "snapshot_digest"
            })
            with self.subTest(field=field):
                with self.assertRaises(SDKStudyError):
                    compare_custody(old, forged)

    def test_added_removed_document_never_reuses_unreviewed_source(self):
        original = build({"a" * 64: fixture()})
        extra = fixture()
        extra["document"] = "manual/appendix.md"
        next_version = build({"a" * 64: fixture(), "b" * 64: extra})
        self.assertEqual(compare_custody(original, next_version)["changes"][0]["change"],
                         "new_document_requires_review")
        self.assertEqual(compare_custody(next_version, original)["changes"][0]["change"],
                         "document_removed_or_deauthorized")


if __name__ == "__main__":
    unittest.main()
