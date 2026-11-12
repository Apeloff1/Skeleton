"""Deterministic negative tests for the first-run source-only handoff guard."""
from __future__ import annotations

import copy
import unittest

from skeleton.app.consumer_first_run_handoff import (
    FirstRunHandoffContractError,
    REQUIRED_FALSE,
    MANDATORY_HOLDS,
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
        "release_holds": sorted(MANDATORY_HOLDS),
        "project_id": "offline-first-playable",
        "action_count": 2,
        "runtime_observation": {"posix_nofollow_available": True,
                                "operating_system": "Linux", "machine": "x86_64",
                                "python": "3.12.0"},
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
    def test_canonical_identifier_and_python_version_acceptance(self):
        for project_id in ("offline-first-playable", "world:act_01", "A", "x" * 128):
            with self.subTest(project_id=project_id):
                evidence = valid_evidence()
                evidence["project_id"] = project_id
                validate_source_only_handoff(evidence)
        for version in ("3.11.9", "3.12.0", "3.13.10"):
            with self.subTest(version=version):
                evidence = valid_evidence()
                evidence["runtime_observation"]["python"] = version
                validate_source_only_handoff(evidence)

    def test_identifier_and_version_regex_do_not_accept_escapes(self):
        for project_id in ("x\\\\Z", "x\\\\d", "x\\n", "x/y"):
            with self.subTest(project_id=project_id):
                evidence = valid_evidence()
                evidence["project_id"] = project_id
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)
        for version in ("3x12x0", "3.12", "v3.12.0", "3.12.0-extra"):
            with self.subTest(version=version):
                evidence = valid_evidence()
                evidence["runtime_observation"]["python"] = version
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

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

    def test_project_identifier_and_action_bounds(self):
        for value in (None, "", "../escape", "a" * 129, 1, "with space"):
            with self.subTest(project_id=value):
                evidence = valid_evidence()
                evidence["project_id"] = value
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)
        for value in (None, False, True, 0, 65, 1.5, "2"):
            with self.subTest(action_count=value):
                evidence = valid_evidence()
                evidence["action_count"] = value
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_every_mandatory_release_hold_is_required(self):
        for hold in MANDATORY_HOLDS:
            with self.subTest(hold=hold):
                evidence = valid_evidence()
                evidence["release_holds"].remove(hold)
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_runtime_observation_types_are_enforced(self):
        for name, value in (("operating_system", None), ("machine", ""),
                            ("python", "unknown"), ("python", 3)):
            with self.subTest(name=name, value=value):
                evidence = valid_evidence()
                evidence["runtime_observation"][name] = value
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_receipt_envelope_and_release_holds_are_bounded(self):
        mutations = (
            lambda e: e.update({f"extra_{i}": i for i in range(65)}),
            lambda e: e.update({"x" * 97: True}),
            lambda e: e.update({1: "non-string key"}),
            lambda e: e.update({"release_holds": sorted(MANDATORY_HOLDS) + [
                f"OPTIONAL_{i}" for i in range(33)]}),
            lambda e: e.update({"release_holds": sorted(MANDATORY_HOLDS) + [
                "x" * 129]}),
            lambda e: e["runtime_observation"].update({"machine": "x" * 65}),
            lambda e: e["runtime_observation"].update({"operating_system": "x" * 65}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                evidence = valid_evidence()
                mutate(evidence)
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_bounded_optional_holds_remain_accepted(self):
        evidence = valid_evidence()
        evidence["release_holds"].append("ADDITIONAL_SECURITY_REVIEW")
        validate_source_only_handoff(evidence)

    def test_release_hold_tokens_reject_ambiguous_unicode_and_controls(self):
        for token in ("optional security review", "optional-security-review",
                      "REVIEW\\nPASSED", "RÉVIEW", "REVIEW\\x00", "review"):
            with self.subTest(token=token):
                evidence = valid_evidence()
                evidence["release_holds"].append(token)
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_runtime_observation_rejects_unexpected_claims(self):
        for key, value in (("device_qualified", True),
                           ("release_certified", True),
                           ("operator_secret", "private"),
                           (42, "invalid key")):
            with self.subTest(key=key):
                evidence = valid_evidence()
                evidence["runtime_observation"][key] = value
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_unknown_top_level_fields_cannot_smuggle_qualification(self):
        for name, value in (
            ("device_qualified", True),
            ("installer_signed", True),
            ("release_ready", True),
            ("secret", "do-not-persist"),
            ("future_schema_extension", {}),
        ):
            with self.subTest(name=name):
                evidence = valid_evidence()
                evidence[name] = value
                with self.assertRaisesRegex(
                    FirstRunHandoffContractError, "unknown or missing evidence fields"
                ):
                    validate_source_only_handoff(evidence)

    def test_missing_required_fields_rejected_before_consumer_use(self):
        for name in tuple(valid_evidence()):
            with self.subTest(name=name):
                evidence = valid_evidence()
                del evidence[name]
                with self.assertRaises(FirstRunHandoffContractError):
                    validate_source_only_handoff(evidence)

    def test_read_only_input(self):
        evidence = valid_evidence()
        original = copy.deepcopy(evidence)
        validate_source_only_handoff(evidence)
        self.assertEqual(evidence, original)


if __name__ == "__main__":
    unittest.main()
