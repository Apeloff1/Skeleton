"""Adversarial offline exact-head evidence acceptance and release-denial cases.

Fixtures are synthetic *negative/policy* exercises, never historical passes.
No fixture asserts that real GitHub checks or devices have succeeded.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.check_reconciliation_exact_head import (
    CHAIN, EXTRA_WORKFLOWS, EvidenceHold, MAX_BYTES,
    REQUIRED_MERGE_JOBS, REPO, SCHEMA, parse,
    read_required_workflows, validate,
)


def evidence_fixture() -> dict:
    """Construct self-consistent hypothetical checks to exercise the parser."""
    required = read_required_workflows()
    heads = {
        5074: "a" * 40,
        5081: "b" * 40,
        5089: "c" * 40,
    }
    rows = []
    for number in CHAIN:
        workflows = []
        wanted = set(required)
        if number == 5089:
            wanted.update(EXTRA_WORKFLOWS)
        for run_id, name in enumerate(sorted(wanted), start=1000):
            jobs = sorted(REQUIRED_MERGE_JOBS) if name == "Merge Readiness" else [
                f"{name} qualification",
            ]
            workflows.append({
                "name": name,
                "head_sha": heads[number],
                "status": "completed",
                "conclusion": "success",
                "run_id": number * 1000 + run_id,
                "run_attempt": 1,
                "jobs": [{
                    "name": job,
                    "head_sha": heads[number],
                    "status": "completed",
                    "conclusion": "success",
                } for job in jobs],
            })
        rows.append({
            "number": number,
            "head_sha": heads[number],
            "base_head_sha": {
                5074: "d" * 40,
                5081: heads[5074],
                5089: heads[5081],
            }[number],
            "draft": number != 5074,
            "merged": False,
            "workflows": workflows,
        })
    return {
        "schema": SCHEMA,
        "repository": REPO,
        "source": "github_api_export_review_only",
        "admission": "review_only",
        "merge_authorized": False,
        "release_authorized": False,
        "pr_chain": rows,
    }


class ExactHeadEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = evidence_fixture()

    def must_hold(self, reason: str) -> None:
        with self.subTest(reason=reason):
            with self.assertRaises(EvidenceHold):
                validate(self.bundle)

    def workflow(self, number: int, name: str) -> dict:
        row = next(row for row in self.bundle["pr_chain"]
                   if row["number"] == number)
        return next(w for w in row["workflows"] if w["name"] == name)

    def test_mock_success_is_only_structural_review_not_approval(self):
        result = validate(self.bundle)
        self.assertEqual(result["source_check_inventory"],
                         "structurally_complete_only")
        self.assertEqual(set(map(int, result["head_shas"])), set(CHAIN))
        for forbidden in ("merge_authorized", "release_authorized",
                          "native_or_device_certified"):
            self.assertIs(result[forbidden], False, forbidden)
        self.assertIn("denied", result["approval"])

    def test_checked_in_policy_requires_all_ten_mandatory_workflows(self):
        policy = read_required_workflows()
        self.assertEqual(len(policy), 10)
        self.assertIn("Sealed Context Guard", policy)
        self.assertIn("Dependency Review", policy)

    def test_custom_gate_override_cannot_downgrade_mandatory_checks(self):
        weak = frozenset(f"untrusted-gate-{i}" for i in range(15))
        with self.assertRaises(EvidenceHold):
            validate(self.bundle, required=weak)

    def test_parent_commit_drift_denied(self):
        self.bundle["pr_chain"][1]["base_head_sha"] = "e" * 40
        self.must_hold("parent head changed before review")

    def test_child_commit_drift_denied(self):
        self.bundle["pr_chain"][2]["base_head_sha"] = "e" * 40
        self.must_hold("child stacked on superseded parent")

    def test_ancestor_workflow_success_never_qualifies(self):
        self.workflow(5089, "Merge Readiness")["head_sha"] = "e" * 40
        self.must_hold("ancestor workflow")

    def test_ancestor_job_success_never_qualifies(self):
        self.workflow(5089, "Merge Readiness")["jobs"][0]["head_sha"] = "e" * 40
        self.must_hold("ancestor job")

    def test_pending_cancelled_skipped_failed_workflows_denied(self):
        for status, conclusion in (
            ("queued", None), ("pending", None),
            ("in_progress", None), ("completed", "cancelled"),
            ("completed", "skipped"), ("completed", "failure"),
            ("completed", "neutral"), ("completed", None),
        ):
            with self.subTest(status=status, conclusion=conclusion):
                item = self.workflow(5089, "Merge Readiness")
                item["status"], item["conclusion"] = status, conclusion
                with self.assertRaises(EvidenceHold):
                    validate(self.bundle)
                item["status"], item["conclusion"] = "completed", "success"

    def test_skipped_security_job_denied_even_if_workflow_green(self):
        item = self.workflow(5089, "Merge Readiness")
        item["jobs"][0]["conclusion"] = "skipped"
        self.must_hold("green summary hides skipped shard")

    def test_all_eight_canonical_shards_required(self):
        item = self.workflow(5089, "Merge Readiness")
        item["jobs"] = [j for j in item["jobs"]
                        if j["name"] != "Canonical Domain Suite (7)"]
        self.must_hold("missing canonical shard")

    def test_missing_dependency_review_denied(self):
        self.bundle["pr_chain"][0]["workflows"] = [
            w for w in self.bundle["pr_chain"][0]["workflows"]
            if w["name"] != "Dependency Review"
        ]
        self.must_hold("dependency review omitted")

    def test_missing_mirror_job_denied_only_on_source_convergence_child(self):
        self.bundle["pr_chain"][2]["workflows"] = [
            w for w in self.bundle["pr_chain"][2]["workflows"]
            if w["name"] != "Jeeves native SQLite source qualification"
        ]
        self.must_hold("native source acceptance absent")

    def test_duplicate_workflow_can_not_hide_failure(self):
        row = self.bundle["pr_chain"][2]
        row["workflows"].append(deepcopy(row["workflows"][0]))
        self.must_hold("duplicated successful workflow")

    def test_duplicate_job_can_not_hide_failure(self):
        item = self.workflow(5089, "Merge Readiness")
        item["jobs"].append(deepcopy(item["jobs"][0]))
        self.must_hold("duplicated successful job")

    def test_false_approval_and_release_denied(self):
        for key in ("merge_authorized", "release_authorized"):
            with self.subTest(key=key):
                self.bundle[key] = True
                with self.assertRaises(EvidenceHold):
                    validate(self.bundle)
                self.bundle[key] = False

    def test_quiet_conversion_to_merged_branch_denied(self):
        self.bundle["pr_chain"][1]["merged"] = True
        self.must_hold("merged before independent review")

    def test_numeric_bool_type_confusion_denied(self):
        item = self.workflow(5089, "Merge Readiness")
        item["run_id"] = True
        self.must_hold("boolean is not a numeric run id")

    def test_zero_attempt_and_bogus_sha_denied(self):
        item = self.workflow(5089, "Merge Readiness")
        item["run_attempt"] = 0
        self.must_hold("invalid run attempt")
        item["run_attempt"] = 1
        self.bundle["pr_chain"][2]["head_sha"] = "bad"
        self.must_hold("invalid commit identity")

    def test_missing_duplicate_and_extra_prs_denied(self):
        self.bundle["pr_chain"][1]["number"] = 5074
        self.must_hold("duplicate parent")
        self.bundle = evidence_fixture()
        self.bundle["pr_chain"].append(deepcopy(self.bundle["pr_chain"][2]))
        self.must_hold("unadmitted extra PR")

    def test_nonfinite_and_duplicate_json_fields_denied(self):
        for raw in (
            b'{"schema":"x","schema":"y"}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":-Infinity}',
            b'not json',
            b"",
            b"{" + b"x" * MAX_BYTES + b"}",
        ):
            with self.subTest(sample=raw[:30]):
                with self.assertRaises(EvidenceHold):
                    parse(raw)

    def test_parser_accepts_valid_but_untrusted_structural_input(self):
        data = parse(json.dumps(self.bundle, sort_keys=True).encode("utf-8"))
        self.assertEqual(data["admission"], "review_only")
        self.assertIs(validate(data)["release_authorized"], False)

    def test_rejects_renamed_repository_and_untrusted_provenance(self):
        self.bundle["repository"] = "attacker/repo"
        self.must_hold("foreign repository")
        self.bundle = evidence_fixture()
        self.bundle["source"] = "signed_release"
        self.must_hold("fabricated source of truth")


if __name__ == "__main__":
    unittest.main()
