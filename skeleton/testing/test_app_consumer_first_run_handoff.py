"""Deterministic negative tests for the first-run source-only handoff guard."""
from __future__ import annotations

import copy
import unittest

from skeleton.app.consumer_first_run_handoff import (
    FirstRunHandoffContractError,
    REQUIRED_FALSE,
    REQUIRED_TRUE,
    SCHEMA,
    validate_source_only_handoff,
)


def valid_evidence():
    sha = "a" * 64
    evidence = {
        "schema": SCHEMA,
        "status": "source_level_first_run_replayed_release_blocked",
        "files_published": 0,
        "source_level_replay_passes": 2,
        "release_holds": ["NATIVE_DEVICE_QUALIFICATION_ABSENT"],
        "runtime_observation": {"posix_nofollow_available": True},
    }
    evidence.update({name: False for name in REQUIRED_FALSE})
    evidence.update({name: True for name in REQUIRED_TRUE})
    evidence.update({name: sha for name in (
        "manifest_sha256", "archive_sha256", "save_sha256",
        "receipt_sha256", "world_digest", "replay_digest",
        "installed_tree_snapshot_sha256",
    )})
    return evidence


class FirstRunHandoffTests(unittest.TestCase):
    def test_valid_source_only_evidence(self):
        evidence = valid_evidence()
        self.assertIsNone(validate_source_only_handoff(evidence))

    def test_every_device_or_release_claim_fails_closed(self):
        for name in REQUIRED_FALSE:
            with self.subTest(name=name):
                evidence = valid_evidence()
                evidence[name] = True
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_every_required_source_proof_fails_closed(self):
        for name in REQUIRED_TRUE:
            with self.subTest(name=name):
                evidence = valid_evidence()
                evidence.pop(name)
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_digest_mutation_and_missing_digest_rejected(self):
        for name in (
            "manifest_sha256", "archive_sha256", "save_sha256",
            "receipt_sha256", "world_digest", "replay_digest",
            "installed_tree_snapshot_sha256",
        ):
            for value in (None, "", "A" * 64, "0" * 63, 123):
                with self.subTest(name=name, value=value):
                    evidence = valid_evidence()
                    evidence[name] = value
                    with self.assertRaises(FirstRunHandoffContractError):
                        validate_source_only_handoff(evidence)

    def test_boolean_integer_confusion_rejected(self):
        for field, value in (("files_published", False), ("source_level_replay_passes", True)):
            evidence = valid_evidence()
            evidence[field] = value
            with self.assertRaises(FirstRunHandoffContractError):
                validate_source_only_handoff(evidence)

    def test_release_holds_missing_or_duplicated(self):
        for holds in ([], None, ["x", "x"], [""], ["x", 3]):
            evidence = valid_evidence()
            evidence["release_holds"] = holds
            with self.assertRaises(FirstRunHandoffContractError):
                validate_source_only_handoff(evidence)

    def test_bad_status_and_observation(self):
        for field, value in (
            ("schema", "unrecognized"),
            ("status", "release_certified"),
            ("runtime_observation", {}),
        ):
            evidence = valid_evidence()
            evidence[field] = value
            with self.assertRaises(FirstRunHandoffContractError):
                validate_source_only_handoff(evidence)

    def test_read_only_input(self):
        evidence = valid_evidence()
        original = copy.deepcopy(evidence)
        validate_source_only_handoff(evidence)
        self.assertEqual(evidence, original)


if __name__ == "__main__":
    unittest.main()
