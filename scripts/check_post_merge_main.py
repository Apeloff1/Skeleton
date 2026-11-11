#!/usr/bin/env python3
"""Read-only post-merge exact-main workflow evidence, never release approval.

Only completed, successful *push* runs for the current canonical main SHA can
contribute to this report. Required real jobs must also succeed. The tool
does not merge, change protection, cancel jobs, or infer first-install
readiness from static checks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import quote
from urllib.request import Request, urlopen


SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_API_PAGES = 10
MAX_PAGE_ITEMS = 100
ESSENTIAL_JOBS: Mapping[str, tuple[str, ...]] = {
    "Workflow Input Security": ("Workflow input shell boundary",),
    "Merge Readiness": (
        "PR Automation Tests", "Unit", "Integration Smoke",
    ),
    "Repository Hygiene Gate": ("Changed-files hygiene",),
    "Malware Gate": ("Reject malware, executable and active-content payloads",),
    "Secret scanning": ("Gitleaks",),
    "App Foundation E2E": ("App Foundation E2E (stack + Playwright)",),
}


class EvidenceError(ValueError):
    """No authority can be inferred from malformed or incomplete evidence."""


def _sha(payload: Mapping[str, Any]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    commit = payload.get("commit")
    value = commit.get("sha") if isinstance(commit, Mapping) else None
    return value if isinstance(value, str) and SHA.fullmatch(value) else None


def _latest_run(
    name: str, head: str, runs: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidates = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        if run.get("name") != name or run.get("event") != "push":
            continue
        if run.get("head_sha") != head:
            continue
        rid = run.get("id")
        attempt = run.get("run_attempt")
        created = run.get("created_at")
        updated = run.get("updated_at")
        if (type(rid) is not int or rid <= 0
                or type(attempt) is not int or attempt < 1
                or not isinstance(created, str)
                or not isinstance(updated, str)
                or len(created) < 20 or len(updated) < 20):
            continue
        # A retry of an older run can finish after a newer run; choosing only
        # by creation date would trust an earlier success over a later failure.
        candidates.append((updated, created, rid, attempt, run))
    if not candidates:
        return None
    return max(candidates, key=lambda row: row[:4])[4]


def inspect(
    *,
    head: str,
    branch_before: Mapping[str, Any],
    branch_after: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    jobs_by_run: Mapping[str, Sequence[Mapping[str, Any]]],
    protection_detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce an auditable, fail-closed report with deterministic reasons."""
    if not isinstance(head, str) or SHA.fullmatch(head) is None:
        raise EvidenceError("invalid exact-main SHA")
    if (not isinstance(branch_before, Mapping)
            or not isinstance(branch_after, Mapping)
            or not isinstance(runs, list)
            or not isinstance(jobs_by_run, Mapping)):
        raise EvidenceError("malformed exact-main evidence shape")
    reasons: list[str] = []
    if _sha(branch_before) != head:
        reasons.append("main_head_before_not_exact")
    if _sha(branch_after) != head:
        reasons.append("main_head_after_changed")
    if branch_before.get("protected") is not True or branch_after.get("protected") is not True:
        reasons.append("main_branch_unprotected")
    # A protected label alone does not prove that named checks bind all writers.
    protection = branch_after.get("protection")
    required_status = protection.get("required_status_checks") if isinstance(protection, Mapping) else None
    checks = set()
    enforcement = None
    if isinstance(required_status, Mapping):
        enforcement = required_status.get("enforcement_level")
        for field in ("contexts", "checks"):
            values = required_status.get(field)
            if isinstance(values, list):
                for item in values:
                    if type(item) is str:
                        checks.add(item)
                    elif isinstance(item, Mapping) and type(item.get("context")) is str:
                        checks.add(item["context"])
    if enforcement != "everyone":
        reasons.append("main_required_checks_not_enforced_for_everyone")
    if not isinstance(protection_detail, Mapping):
        reasons.append("main_protection_detail_unverified")
    else:
        admins = protection_detail.get("enforce_admins")
        reviews = protection_detail.get("required_pull_request_reviews")
        strict_status = protection_detail.get("required_status_checks")
        if not isinstance(admins, Mapping) or admins.get("enabled") is not True:
            reasons.append("main_admin_bypass_not_fenced")
        if (not isinstance(reviews, Mapping)
                or type(reviews.get("required_approving_review_count")) is not int
                or reviews["required_approving_review_count"] < 1):
            reasons.append("main_independent_review_not_required")
        elif reviews.get("dismiss_stale_reviews") is not True:
            reasons.append("main_stale_review_dismissal_missing")
        if not isinstance(strict_status, Mapping) or strict_status.get("strict") is not True:
            reasons.append("main_up_to_date_required_status_checks_missing")
        conversations = protection_detail.get("required_conversation_resolution")
        if (not isinstance(conversations, Mapping)
                or conversations.get("enabled") is not True):
            reasons.append("main_conversation_resolution_not_required")
    # Branch protection binds *check-run job contexts*, not the display
    # title of the containing workflow. Requiring workflow titles would
    # incorrectly reject a correctly protected repository.
    for workflow, job_names in ESSENTIAL_JOBS.items():
        for job in job_names:
            if job not in checks:
                reasons.append(
                    "main_required_check_not_configured:" + workflow + ":" + job
                )

    evidence: dict[str, dict[str, Any]] = {}
    for name, jobs_required in ESSENTIAL_JOBS.items():
        run = _latest_run(name, head, runs)
        if run is None:
            reasons.append("exact_main_push_workflow_missing:" + name)
            evidence[name] = {"state": "missing"}
            continue
        run_id = run["id"]
        status, conclusion = run.get("status"), run.get("conclusion")
        evidence[name] = {
            "run_id": run_id, "attempt": run["run_attempt"],
            "status": status, "conclusion": conclusion,
        }
        if status != "completed" or conclusion != "success":
            reasons.append("exact_main_workflow_not_success:" + name)
            continue
        jobs = jobs_by_run.get(str(run_id))
        if not isinstance(jobs, list):
            reasons.append("exact_main_job_inventory_missing:" + name)
            continue
        # A workflow-level pass does not confer authority on a job from an
        # ancestor commit, another run, or a superseded retry attempt.
        for job in jobs:
            if (not isinstance(job, Mapping)
                    or type(job.get("run_id")) is not int
                    or job.get("run_id") != run_id
                    or type(job.get("run_attempt")) is not int
                    or job.get("run_attempt") != run["run_attempt"]
                    or job.get("head_sha") != head):
                reasons.append("exact_main_job_origin_mismatch:" + name)
                break
        names: dict[str, Mapping[str, Any]] = {}
        duplicate_names = set()
        for job in jobs:
            if not isinstance(job, Mapping) or not isinstance(job.get("name"), str):
                continue
            if job["name"] in names:
                duplicate_names.add(job["name"])
            names[job["name"]] = job
        if duplicate_names:
            reasons.append("ambiguous_duplicate_job_identity:" + name)
        for required in jobs_required:
            job = names.get(required)
            if job is None or job.get("status") != "completed" or job.get("conclusion") != "success":
                reasons.append("essential_job_not_success:" + name + ":" + required)
        if name == "Merge Readiness":
            # All eight domain shards are part of the canonical current-head
            # qualification. One green shard is never proof of a green suite.
            required_shards = {
                "Canonical Domain Suite (" + str(index) + ")"
                for index in range(8)
            }
            seen_shards = set()
            for job in jobs:
                if (not isinstance(job, Mapping)
                        or not isinstance(job.get("name"), str)
                        or not job["name"].startswith("Canonical Domain Suite (")):
                    continue
                shard = job["name"]
                seen_shards.add(shard)
                if shard not in required_shards:
                    reasons.append("unexpected_canonical_domain_shard:" + shard)
                if job.get("status") != "completed" or job.get("conclusion") != "success":
                    reasons.append("canonical_domain_suite_not_success:" + shard)
            for missing in sorted(required_shards - seen_shards):
                reasons.append("canonical_domain_suite_evidence_missing:" + missing)

    reasons = list(dict.fromkeys(reasons))
    return {
        "schema": "skeleton.post-merge-main-evidence.v1",
        "exact_main_sha": head,
        "current_main_unchanged": _sha(branch_before) == head == _sha(branch_after),
        "workflow_evidence": evidence,
        "blocking_reasons": reasons,
        "exact_main_workflow_gates_qualified": not reasons,
        "first_install_certified": False,
        "production_release_approved": False,
    }


def _get_json(repo: str, suffix: str, token: str | None) -> dict[str, Any]:
    url = "https://api.github.com/repos/" + "/".join(quote(p, safe="") for p in repo.split("/")) + suffix
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "skeleton-readonly-exact-main-audit"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=15) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise EvidenceError("GitHub response exceeded byte budget")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise EvidenceError("unexpected GitHub evidence response")
    return value


def _paged_items(
    repo: str,
    path: str,
    key: str,
    token: str | None,
) -> list[dict[str, Any]]:
    """Read a bounded consistent GitHub Actions inventory, never truncate it.

    A changing total_count or repeated IDs is an evidence race, not permission
    to use an arbitrary first page as a qualifying run inventory.
    """
    items: list[dict[str, Any]] = []
    expected_total: int | None = None
    seen: set[int] = set()
    for page in range(1, MAX_API_PAGES + 1):
        separator = "&" if "?" in path else "?"
        result = _get_json(
            repo, path + separator + "per_page=" + str(MAX_PAGE_ITEMS)
            + "&page=" + str(page), token,
        )
        total = result.get("total_count")
        batch = result.get(key)
        if type(total) is not int or total < 0 or not isinstance(batch, list):
            raise EvidenceError("GitHub Actions inventory has invalid shape")
        if expected_total is None:
            expected_total = total
        if total != expected_total or len(batch) > MAX_PAGE_ITEMS:
            raise EvidenceError("GitHub Actions inventory changed during pagination")
        for item in batch:
            if not isinstance(item, dict):
                raise EvidenceError("GitHub Actions item must be an object")
            ident = item.get("id")
            if type(ident) is not int or ident <= 0 or ident in seen:
                raise EvidenceError("GitHub Actions inventory duplicate or invalid ID")
            seen.add(ident)
            items.append(item)
        if len(items) == total:
            return items
        if len(items) > total or not batch:
            raise EvidenceError("GitHub Actions inventory has missing or duplicated pages")
    raise EvidenceError("GitHub Actions inventory exceeded bounded pagination")


def live_snapshot(repo: str, head: str | None = None) -> dict[str, Any]:
    if not REPO.fullmatch(repo):
        raise EvidenceError("repository must be owner/name")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    before = _get_json(repo, "/branches/main", token)
    expected = _sha(before)
    if expected is None or (head is not None and head != expected):
        raise EvidenceError("current main head does not match requested SHA")
    runs = _paged_items(
        repo, "/actions/runs?head_sha=" + expected + "&event=push",
        "workflow_runs", token,
    )
    jobs_by_run: dict[str, list[dict[str, Any]]] = {}
    for name in ESSENTIAL_JOBS:
        match = _latest_run(name, expected, runs)
        if match is None or match.get("conclusion") != "success" or match.get("status") != "completed":
            continue
        run_id = match["id"]
        jobs_by_run[str(run_id)] = _paged_items(
            repo, "/actions/runs/" + str(run_id) + "/jobs",
            "jobs", token,
        )
    # /branches/main is an abbreviated projection: it cannot establish
    # enforce_admins, review policy, up-to-date status or conversation fencing.
    # Missing credentials, 404 and forbidden policy reads must fail closed.
    protection_detail = _get_json(repo, "/branches/main/protection", token)
    after = _get_json(repo, "/branches/main", token)
    return {
        "head": expected, "branch_before": before, "branch_after": after,
        "runs": runs, "jobs_by_run": jobs_by_run,
        "protection_detail": protection_detail,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Apeloff1/Skeleton")
    parser.add_argument("--sha", help="Require this exact main commit")
    parser.add_argument("--snapshot", help="Offline JSON evidence fixture (no network)")
    args = parser.parse_args(argv)
    try:
        if args.snapshot:
            from pathlib import Path
            source = Path(args.snapshot)
            with source.open("rb") as stream:
                raw = stream.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise EvidenceError("offline evidence exceeds byte budget")
            snapshot = json.loads(raw)
            if not isinstance(snapshot, dict):
                raise EvidenceError("offline evidence must be an object")
            if args.sha and args.sha != snapshot.get("head"):
                raise EvidenceError("offline main SHA mismatch")
        else:
            snapshot = live_snapshot(args.repo, args.sha)
        report = inspect(**snapshot)
        if args.snapshot:
            # Synthetic fixtures are useful for testing the decision function,
            # but must never become a green operational or release receipt.
            report["evidence_mode"] = "offline_fixture"
            report["exact_main_workflow_gates_qualified"] = False
            report["blocking_reasons"].append("offline_fixture_not_authoritative")
        else:
            report["evidence_mode"] = "live_github_api"
    except (EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
        # Never echo API credentials or remote response text in public logs.
        print(json.dumps({
            "schema": "skeleton.post-merge-main-evidence.v1",
            "exact_main_workflow_gates_qualified": False,
            "first_install_certified": False,
            "production_release_approved": False,
            "blocking_reasons": ["evidence_fetch_or_shape_failure:" + type(exc).__name__],
        }, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["exact_main_workflow_gates_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
