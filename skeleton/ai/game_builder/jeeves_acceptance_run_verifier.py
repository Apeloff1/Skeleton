"""Independent GitHub Actions acceptance evidence validation (pure verifier).

Unlike the matrix runner, this module never trusts a self-reported "passed"
boolean. A privileged caller must obtain the run, jobs and the two artifact
payloads from authenticated GitHub REST endpoints. The standalone CLI is that
caller. Exact-head regression acceptance is not an installed-app release gate.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import re
from typing import Any, Mapping

from .jeeves_appwide_fabric import JeevesAppwideError, digest

SCHEMA = "skeleton.ai.app_acceptance_verified_ci.v1"
REPOSITORY = "Apeloff1/Skeleton"
WORKFLOW = "Jeeves App Acceptance Matrix"
WORKFLOW_PATH = ".github/workflows/jeeves-app-acceptance-matrix.yml"
OS_TARGETS = ("Linux", "Windows")
JOB_NAMES = {
    "Linux": "Selected real product regressions (ubuntu-24.04)",
    "Windows": "Selected real product regressions (windows-2022)",
}
EXPECTED_STEP = "Execute actual curated family regression suite"
HEX40 = re.compile(r"^[a-f0-9]{40}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")


def _valid_sha(value: Any, n: int) -> bool:
    return type(value) is str and bool(
        (HEX40 if n == 40 else HEX64).fullmatch(value))


def _positive_identifier(value: Any) -> bool:
    return type(value) is int and 0 < value < (1 << 63)


def _require(condition: bool, error: str):
    if not condition:
        raise JeevesAppwideError("independent CI verification rejected: " + error)


def _receipt_digest(report: Mapping[str, Any]) -> str:
    content = {k: v for k, v in report.items() if k != "receipt_sha256"}
    return sha256(json.dumps(content, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def verify(
    *,
    head: str,
    run: Mapping[str, Any],
    jobs: list[Mapping[str, Any]],
    evidence_by_os: Mapping[str, Mapping[str, Any]],
    expected_matrix: Mapping[str, Any],
    expected_run_id: int,
    expected_attempt: int,
) -> dict[str, Any]:
    """Validate independent *source-originated* GitHub observations.

    This pure function cannot authenticate its inputs. The authorized
    network caller must fetch all inputs directly from GitHub's HTTPS API.
    A successful verification only covers scheduled candidate regression
    modules and their source identity, not functional product-family release.
    """
    _require(_valid_sha(head, 40), "invalid exact commit SHA")
    _require(_positive_identifier(expected_run_id) and
             _positive_identifier(expected_attempt), "invalid run identifiers")
    _require(type(run) is dict and type(jobs) is list and
             type(evidence_by_os) is dict and type(expected_matrix) is dict,
             "invalid independent observation types")
    repo = run.get("repository")
    _require(type(repo) is dict and repo.get("full_name") == REPOSITORY,
             "run repository mismatch")
    _require(run.get("id") == expected_run_id and
             run.get("run_attempt") == expected_attempt and
             run.get("head_sha") == head and
             run.get("name") == WORKFLOW and
             run.get("event") in ("pull_request", "workflow_dispatch") and
             run.get("status") == "completed" and
             run.get("conclusion") == "success", "run not exact-head successful")
    path = run.get("path")
    _require(type(path) is str and
             (path == WORKFLOW_PATH or
              path.startswith(REPOSITORY + "/" + WORKFLOW_PATH + "@")),
             "unexpected workflow source path")
    _require(len(jobs) >= 2 and len(jobs) <= 100, "required job list incomplete")
    _require(set(evidence_by_os) == set(OS_TARGETS), "required OS artifacts incomplete")
    selected = expected_matrix.get("selected_modules")
    receipts = expected_matrix.get("module_source_receipts")
    _require(type(selected) is list and selected and
             len(selected) == len(set(selected)) and all(
                 type(m) is str and m.startswith("tests.test_") for m in selected),
             "invalid selected source-bound test suite")
    _require(type(receipts) is list and receipts and
             type(expected_matrix.get("matrix_digest", "")) is str and
             _valid_sha(expected_matrix.get("matrix_digest"), 64) and
             _valid_sha(expected_matrix.get("matrix_sha256"), 64) and
             _valid_sha(expected_matrix.get("scope_sha256"), 64),
             "invalid expected acceptance source receipts")
    _require(expected_matrix.get("scheduled_test_module_count") == len(selected),
             "source matrix scheduled module count drift")
    allowed_receipts = {p["path"]: p["sha256"] for p in receipts
                        if type(p) is dict and type(p.get("path")) is str and
                        _valid_sha(p.get("sha256"), 64)}
    _require(len(allowed_receipts) == len(receipts), "duplicate/malformed source receipts")
    expected_result_keys = {"module", "command", "started_utc", "ended_utc",
                            "return_code", "timed_out", "subprocess_executed",
                            "targeted_tests_passed_in_runner", "stdout", "stderr",
                            "independent_ci_provenance_verified_by_this_script"}
    verified_os = []
    for operating_system in OS_TARGETS:
        name = JOB_NAMES[operating_system]
        matches = [j for j in jobs if j.get("name") == name]
        _require(len(matches) == 1, "missing/duplicate required OS CI job " + name)
        job = matches[0]
        _require(job.get("run_id") == expected_run_id and
                 job.get("run_attempt") == expected_attempt and
                 job.get("head_sha") == head and
                 job.get("status") == "completed" and
                 job.get("conclusion") == "success",
                 "required operating-system job not successful")
        steps = job.get("steps")
        _require(type(steps) is list and sum(
            step.get("name") == EXPECTED_STEP and
            step.get("conclusion") == "success" for step in steps
            if type(step) is dict) == 1, "targeted real test step never passed")
        report = evidence_by_os[operating_system]
        _require(type(report) is dict and report.get("schema") ==
                 "skeleton.ai.app_acceptance_run_evidence.v1",
                 "unrecognized runner result schema")
        _require(report.get("git_head") == head and
                 report.get("expected_head") == head,
                 "runner evidence not bound to exact commit")
        claims = report.get("github_claims")
        _require(type(claims) is dict and
                 claims.get("repository") == REPOSITORY and
                 claims.get("workflow") == WORKFLOW and
                 claims.get("run_id") == str(expected_run_id) and
                 claims.get("run_attempt") == str(expected_attempt) and
                 claims.get("os") == operating_system and
                 report.get("local_mode") is False,
                 "runner evidence not bound to trusted CI context")
        # The full matrix digest includes a checkout file-inventory snapshot,
        # which can differ between Windows and Linux due to OS metadata/EOL.
        # Compare the immutable original SOURCE CONTENT digests instead.
        _require(_valid_sha(report.get("matrix_digest"), 64),
                 "invalid OS-local acceptance matrix digest")
        for field in ("matrix_sha256", "scope_sha256"):
            _require(report.get(field) == expected_matrix.get(field),
                     "acceptance matrix source changed since verified CI")
        _require(report.get("test_source_receipts") == receipts,
                 "test source digests do not match exact-head registry")
        _require(report.get("candidate_modules") == len(selected) and
                 report.get("modules_actually_executed") == len(selected) and
                 report.get("modules_reporting_pass") == len(selected) and
                 report.get("selected_regression_suite_reported_success") is True,
                 "test-result cardinality or pass contract invalid")
        _require(report.get("full_app_completion_percent") is None and
                 report.get("release_device_verified") is False and
                 report.get("user_journeys_verified") is False and
                 report.get("model_weight_promotion_performed") is False,
                 "runner falsely claims product release readiness")
        _require(_valid_sha(report.get("receipt_sha256"), 64) and
                 hmac.compare_digest(_receipt_digest(report), report["receipt_sha256"]),
                 "runner evidence payload digest invalid")
        results = report.get("run_results")
        _require(type(results) is list and len(results) == len(selected) and
                 [row.get("module") for row in results
                  if type(row) is dict] == selected,
                 "executed module ordering differs from reviewed matrix")
        for row in results:
            _require(set(row) == expected_result_keys and
                     row["return_code"] == 0 and
                     type(row["return_code"]) is int and
                     row["timed_out"] is False and
                     row["subprocess_executed"] is True and
                     row["targeted_tests_passed_in_runner"] is True and
                     row["independent_ci_provenance_verified_by_this_script"] is False,
                     "selected test did not really report a clean exit")
            _require(row["command"] == [
                     "python", "-m", "unittest", row["module"], "-q"],
                     "unreviewed executable test command")
            for stream in ("stdout", "stderr"):
                body = row[stream]
                _require(type(body) is dict and
                         _valid_sha(body.get("sha256"), 64) and
                         type(body.get("total_bytes")) is int and
                         body["total_bytes"] >= 0 and
                         body.get("content_stored_in_artifact") is False,
                         "untrusted or sensitive runner-output material")
        verified_os.append({
            "os": operating_system,
            "job_id": job.get("id"),
            "reported_passed_modules": len(results),
            "matrix_digest_local_to_runner": report["matrix_digest"],
            "artifact_sha256": sha256(json.dumps(report, sort_keys=True,
                                     separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest(),
        })
    body = {
        "schema": SCHEMA, "repository": REPOSITORY,
        "verified_git_head": head, "run_id": expected_run_id,
        "run_attempt": expected_attempt,
        "verified_os": verified_os,
        "scheduled_test_modules_independently_confirmed": len(selected),
        "independent_ci_execution_verified": True,
        "targeted_test_evidence_verifiable": True,
        "source_only_not_complete_app": True,
        "family_implementation_test_stage_is_not_whole_family_qualification": True,
        "release_device_qualified": False,
        "trained_model_quality_verified": False,
        "full_app_completion_percent": None,
        "self_signoff_performed": False,
    }
    return {**body, "digest": digest(body)}
