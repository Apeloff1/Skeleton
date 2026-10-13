"""Exact-head independently verified *targeted regression* acceptance rollup.

Never promote a family, masterplan volume, model, or release device solely
because targeted unit/pytest tests passed. This reducer can only combine
authentic CI verification receipts supplied by the trusted operator command.
It has no tool execution, model promotion or GitHub write capabilities.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from .jeeves_appwide_fabric import JeevesAppwideError, digest

SCHEMA = "skeleton.ai.app_targeted_regression_acceptance_rollup.v1"
GITHUB_REPO = "Apeloff1/Skeleton"
FIRST = "skeleton.ai.app_acceptance_verified_ci.v1"
SECOND = "skeleton.ai.app_pytest_acceptance_verified_ci.v1"


def _require(condition, msg):
    if not condition:
        raise JeevesAppwideError("independent acceptance rollup rejected: " + msg)


def _validate_proof(body, *, schema, head):
    _require(type(body) is dict and body.get("schema") == schema
             and body.get("repository") == GITHUB_REPO
             and body.get("verified_git_head") == head
             and body.get("independent_ci_execution_verified") is True
             and body.get("release_device_qualified") is False
             and body.get("full_app_completion_percent") is None,
             "unrecognized, unfinished, or overstated CI proof")
    _require(type(body.get("run_id")) is int and body["run_id"] > 0
             and type(body.get("run_attempt")) is int and body["run_attempt"] > 0,
             "malformed CI run identity")
    rows = body.get("verified_os")
    _require(type(rows) is list and len(rows) == 2 and
             {row.get("os") for row in rows if type(row) is dict} ==
             {"Linux", "Windows"} and
             all(type(row) is dict and type(row.get("job_id")) is int
                 and row["job_id"] > 0 for row in rows),
             "both independent CI platforms must be verified")
    core = {k: v for k, v in body.items() if k != "digest"}
    _require(type(body.get("digest")) is str and
             body["digest"] == digest(core), "CI reducer input digest drift")


def combine(*, head, expected_families, unittest_proof, pytest_proof,
            reviewed_matrix_sha256, reviewed_scope_sha256):
    """Two separately verified runs, one exact reviewed source-and-family plan.

    Input authentication is NOT conferred by this pure function: the privileged
    operator caller must first fetch both GitHub runs and artifacts directly
    through their independent verifiers on a trusted exact-head checkout.
    """
    _require(type(head) is str and len(head) == 40 and
             all(ch in "0123456789abcdef" for ch in head),
             "malformed exact reviewed git head")
    _require(type(reviewed_matrix_sha256) is str and
             len(reviewed_matrix_sha256) == 64 and
             type(reviewed_scope_sha256) is str and
             len(reviewed_scope_sha256) == 64 and
             all(c in "0123456789abcdef"
                 for c in reviewed_matrix_sha256 + reviewed_scope_sha256),
             "untrusted tested source contracts")
    _require(type(expected_families) is list and len(expected_families) == 42
             and len(set(expected_families)) == 42 and
             expected_families == ["F%02d" % i for i in range(1,43)],
             "fixed canonical forty-two family denominator required")
    _validate_proof(unittest_proof, schema=FIRST, head=head)
    _validate_proof(pytest_proof, schema=SECOND, head=head)
    _require(unittest_proof["run_id"] != pytest_proof["run_id"],
             "two execution modes require distinct independently verified runs")
    unittest_ids = unittest_proof.get(
        "targeted_regression_subsets_verified_for_families")
    pytest_ids = pytest_proof.get("pytest_targeted_families")
    _require(type(unittest_ids) is list and type(pytest_ids) is list and
             unittest_ids == sorted(set(unittest_ids)) and
             pytest_ids == sorted(set(pytest_ids)) and
             all(type(item) is str for item in unittest_ids + pytest_ids) and
             bool(unittest_ids) and bool(pytest_ids),
             "reviewed CI family subsets are not canonical")
    found = set(unittest_ids) | set(pytest_ids)
    _require(not set(unittest_ids) & set(pytest_ids) and
             found <= set(expected_families),
             "CI subset lanes are overlapping or outside fixed family scope")
    _require(unittest_proof.get("targeted_family_subset_count") == len(unittest_ids)
             and pytest_proof.get("pytest_targeted_family_count") == len(pytest_ids)
             and unittest_proof.get("family_denominator") == 42
             and pytest_proof.get("family_denominator") == 42,
             "independent subgroup family cardinality drift")
    _require(unittest_proof.get("complete_family_stage_qualifications_admitted") == 0
             and pytest_proof.get("whole_feature_acceptance_admitted") == 0
             and unittest_proof.get(
                 "targeted_subset_is_not_full_feature_implementation_test_acceptance") is True
             and pytest_proof.get("source_subsets_are_not_user_journeys") is True,
             "invalid whole-feature acceptance claim")
    sources = [
        {"runner": "unittest", "run_id": unittest_proof["run_id"],
         "run_attempt": unittest_proof["run_attempt"],
         "verified_subset_family_ids": unittest_ids,
         "digest": unittest_proof["digest"]},
        {"runner": "pytest", "run_id": pytest_proof["run_id"],
         "run_attempt": pytest_proof["run_attempt"],
         "verified_subset_family_ids": pytest_ids,
         "digest": pytest_proof["digest"]},
    ]
    result = {
        "schema": SCHEMA,
        "repository": GITHUB_REPO,
        "exact_head": head,
        "reviewed_matrix_sha256": reviewed_matrix_sha256,
        "reviewed_scope_sha256": reviewed_scope_sha256,
        "family_denominator": 42,
        "verified_targeted_regression_subset_families": len(found),
        "verified_targeted_regression_subset_ids": sorted(found),
        "unverified_targeted_regression_subset_ids": [
            key for key in expected_families if key not in found],
        "independent_targeted_subset_pct": round(100*len(found)/42,2),
        "all_42_targeted_subsets_verified": len(found)==42,
        "independent_original_GitHub_runs_verified": 2,
        "os_job_receipts_verified": 4,
        "source_ci_verification": sources,
        "each_targeted_subset_is_not_full_feature_acceptance": True,
        "actual_complete_family_release_qualifications": 0,
        "independent_end_to_end_user_journeys_in_this_receipt": 0,
        "trained_model_quality_qualified": False,
        "device_install_or_game_export_qualified": False,
        "full_app_completion_percent": None,
        "source_code_or_weights_mutated_by_rollup": False,
        "live_network_called_by_this_reducer": False,
    }
    return {**result, "digest": digest(result)}
