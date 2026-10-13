"""Independent verification of actual Windows/Linux pytest JUnit receipts.

Only a trusted reader of the GitHub Actions HTTPS API may supply observations.
The verifier itself never treats a self-reported artifact as authentication.
Accepted results qualify reviewed *targeted test subsets*, not the app or
end-user feature family as a whole.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
from typing import Any, Mapping

from .jeeves_appwide_fabric import JeevesAppwideError, digest
from .jeeves_acceptance_run_verifier import (
    REPOSITORY, _require, _positive_identifier, _valid_sha, _receipt_digest,
)

SCHEMA = "skeleton.ai.app_pytest_acceptance_verified_ci.v1"
WORKFLOW = "Jeeves App Pytest Acceptance"
WORKFLOW_PATH = ".github/workflows/jeeves-app-pytest-acceptance.yml"
STEP = "Execute actual reviewed pytest family regressions"
JOB_NAMES = {
    "Linux": "Selected source-bound pytest regressions (ubuntu-24.04)",
    "Windows": "Selected source-bound pytest regressions (windows-2022)",
}
EXPECTED_CASE_KEYS = {
    "module", "command", "started_utc", "ended_utc", "return_code",
    "timed_out", "subprocess_executed", "pytest_cases_observed",
    "junit_xml_sha256", "targeted_tests_passed_in_runner",
    "stdout", "stderr", "independent_ci_provenance_verified_by_this_script",
}


def verify_pytest(
    *, head: str, run: Mapping[str, Any], jobs: list[Mapping[str, Any]],
    evidence_by_os: Mapping[str, Mapping[str, Any]],
    expected_matrix: Mapping[str, Any], expected_run_id: int,
    expected_attempt: int,
) -> dict:
    _require(_valid_sha(head, 40) and
             _positive_identifier(expected_run_id) and
             _positive_identifier(expected_attempt), "invalid exact run source identity")
    _require(type(run) is dict and type(jobs) is list and
             type(evidence_by_os) is dict and type(expected_matrix) is dict,
             "invalid independent CI payload types")
    repo = run.get("repository")
    _require(type(repo) is dict and repo.get("full_name") == REPOSITORY and
             run.get("id") == expected_run_id and
             run.get("run_attempt") == expected_attempt and
             run.get("head_sha") == head and
             run.get("name") == WORKFLOW and
             run.get("event") in ("pull_request", "workflow_dispatch") and
             run.get("status") == "completed" and
             run.get("conclusion") == "success", "invalid or incomplete GitHub CI run")
    path = run.get("path")
    _require(type(path) is str and (
        path == WORKFLOW_PATH or
        path.startswith(REPOSITORY + "/" + WORKFLOW_PATH + "@")),
        "GitHub CI workflow source mismatch")
    _require(2 <= len(jobs) <= 100 and set(evidence_by_os) == set(JOB_NAMES),
             "Windows and Linux job or artifact set incomplete")
    modules = expected_matrix.get("pytest_selected_modules")
    receipts = expected_matrix.get("module_source_receipts")
    families = expected_matrix.get("pytest_smoke_families")
    _require(type(modules) is list and 0 < len(modules) <= 80 and
             all(type(item) is str and item.startswith("tests.test_")
                 for item in modules) and len(modules) == len(set(modules)) and
             expected_matrix.get("scheduled_pytest_module_count") == len(modules),
             "unreviewed pytest modules or duplicated modules")
    _require(type(receipts) is list and bool(receipts) and
             all(type(e) is dict and _valid_sha(e.get("sha256"), 64) and
                 type(e.get("path")) is str for e in receipts) and
             len({e["path"] for e in receipts}) == len(receipts) and
             _valid_sha(expected_matrix.get("matrix_sha256"), 64) and
             _valid_sha(expected_matrix.get("scope_sha256"), 64) and
             type(families) is list and 0 < len(families) <= 42 and
             expected_matrix.get("family_denominator") == 42,
             "invalid immutable source receipts or family denominator")
    selected = set(modules)
    family_names = set()
    for family in families:
        _require(type(family) is dict and
                 set(family) == {"family_id", "modules"} and
                 type(family["family_id"]) is str and
                 family["family_id"].startswith("F") and
                 family["family_id"][1:].isdigit() and
                 1 <= int(family["family_id"][1:]) <= 42 and
                 family["family_id"] not in family_names and
                 type(family["modules"]) is list and bool(family["modules"]) and
                 all(type(m) is str and m in selected for m in family["modules"]),
                 "non-reviewed pytest family or test module")
        family_names.add(family["family_id"])
    _require(set(m for f in families for m in f["modules"]) == selected,
             "pytest module not linked to reviewed feature family")
    by_os = []
    for osname, jobname in JOB_NAMES.items():
        matching = [j for j in jobs if type(j) is dict and j.get("name") == jobname]
        _require(len(matching) == 1, "required pytest OS job missing or repeated")
        job = matching[0]
        _require(job.get("run_id") == expected_run_id and
                 job.get("run_attempt") == expected_attempt and
                 job.get("head_sha") == head and
                 job.get("status") == "completed" and
                 job.get("conclusion") == "success",
                 "pytest OS job not exact-head successful")
        steps = job.get("steps")
        _require(type(steps) is list and sum(
            type(s) is dict and s.get("name") == STEP and
            s.get("conclusion") == "success" for s in steps) == 1,
            "actual pytest subprocess step did not complete successfully")
        evidence = evidence_by_os[osname]
        _require(type(evidence) is dict and
                 evidence.get("schema") ==
                 "skeleton.ai.app_pytest_acceptance_run_evidence.v1" and
                 evidence.get("git_head") == head and
                 evidence.get("expected_head") == head and
                 evidence.get("local_mode") is False,
                 "pytest artifact not from exact CI source")
        claims = evidence.get("github_claims")
        _require(type(claims) is dict and
                 claims.get("repository") == REPOSITORY and
                 claims.get("workflow") == WORKFLOW and
                 claims.get("run_id") == str(expected_run_id) and
                 claims.get("run_attempt") == str(expected_attempt) and
                 claims.get("os") == osname,
                 "pytest artifact run identity mismatch")
        _require(evidence.get("matrix_sha256") == expected_matrix["matrix_sha256"] and
                 evidence.get("scope_sha256") == expected_matrix["scope_sha256"] and
                 evidence.get("test_source_receipts") == receipts and
                 evidence.get("pytest_family_count") == len(families) and
                 evidence.get("full_family_denominator") == 42,
                 "pytest artifact source custody does not match checkout")
        _require(evidence.get("candidate_modules") == len(modules) and
                 evidence.get("modules_actually_executed") == len(modules) and
                 evidence.get("modules_reporting_pass") == len(modules) and
                 evidence.get("selected_regression_suite_reported_success") is True and
                 evidence.get("full_app_completion_percent") is None and
                 evidence.get("release_device_verified") is False and
                 evidence.get("user_journeys_verified") is False and
                 evidence.get("model_weight_promotion_performed") is False,
                 "pytest execution counts or release claims are not accepted")
        _require(_valid_sha(evidence.get("receipt_sha256"), 64) and
                 hmac.compare_digest(_receipt_digest(evidence),
                                     evidence["receipt_sha256"]),
                 "pytest artifact payload modified after run")
        results = evidence.get("run_results")
        _require(type(results) is list and len(results) == len(modules) and
                 [item.get("module") for item in results
                  if type(item) is dict] == modules,
                 "pytest result modules disagree with selected reviewed suite")
        total = 0
        for item in results:
            _require(set(item) == EXPECTED_CASE_KEYS and
                     type(item.get("return_code")) is int and
                     item["return_code"] == 0 and item["timed_out"] is False and
                     item["subprocess_executed"] is True and
                     item["targeted_tests_passed_in_runner"] is True and
                     type(item.get("pytest_cases_observed")) is int and
                     0 < item["pytest_cases_observed"] <= 2000 and
                     _valid_sha(item.get("junit_xml_sha256"), 64) and
                     item["independent_ci_provenance_verified_by_this_script"] is False,
                     "one reviewed pytest module executed zero tests or failed")
            _require(item["command"] == [
                "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "-o", "addopts=", item["module"].replace(".", "/") + ".py",
            ], "unreviewed pytest subprocess command")
            for stream in ("stdout", "stderr"):
                row = item[stream]
                _require(type(row) is dict and
                         set(row) == {"sha256", "total_bytes",
                                     "content_stored_in_artifact"} and
                         _valid_sha(row.get("sha256"), 64) and
                         type(row.get("total_bytes")) is int and
                         row["total_bytes"] >= 0 and
                         row.get("content_stored_in_artifact") is False,
                         "unsafe or malformed pytest process output receipt")
            total += item["pytest_cases_observed"]
        _require(type(evidence.get("pytest_cases_observed_total")) is int and
                 total > 0 and evidence["pytest_cases_observed_total"] == total,
                 "pytest JUnit cases missing or inconsistent")
        by_os.append({
            "os": osname,
            "job_id": job.get("id"),
            "confirmed_pytest_modules": len(modules),
            "confirmed_executed_cases": total,
            "artifact_sha256": sha256(json.dumps(evidence, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        })
    final = {
        "schema": SCHEMA, "repository": REPOSITORY,
        "verified_git_head": head, "run_id": expected_run_id,
        "run_attempt": expected_attempt, "verified_os": by_os,
        "pytest_targeted_families": sorted(family_names),
        "pytest_targeted_family_count": len(family_names),
        "family_denominator": 42,
        "pytest_targeted_family_subset_pct": round(
            100 * len(family_names) / 42, 2),
        "independent_ci_execution_verified": True,
        "whole_feature_acceptance_admitted": 0,
        "model_quality_verified": False,
        "release_device_qualified": False,
        "full_app_completion_percent": None,
        "source_subsets_are_not_user_journeys": True,
        "no_ci_actions_performed_by_verifier": True,
    }
    return {**final, "digest": digest(final)}
