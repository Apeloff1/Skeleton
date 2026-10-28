#!/usr/bin/env python3
"""Fail-closed, read-only GitHub source/CI gate for tagged release publication.

The gate is intentionally separate from build reproducibility and from external
production deployment attestation. A passed source gate never asserts that KMS,
witness, restore or real-world deployment qualifications have passed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Callable

REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\\Z")
# These workflows execute on every main push. Path-scoped/PR-only workflows
# are additional negative evidence if present, never invented successes.
REQUIRED_PUSH = ("Merge Readiness", "Malware Gate", "Secret scanning")
PATH_SCOPED = (
    "Workflow Input Security",
    "Repository Hygiene Gate",
    "Backend Quality",
    "App Foundation E2E",
)
REQUIRED_CHECK = "Merge Readiness"
GITHUB_ACTIONS_APP_ID = 15368


def gh_get(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", "--method", "GET", path],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ValueError("GitHub read failed: " + path + "; cannot certify release")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub returned malformed JSON: " + path) from exc


def assess(
    sha: str,
    branch: dict[str, Any],
    workflow_runs: list[dict[str, Any]],
    *,
    branch_name: str = "main",
) -> dict[str, Any]:
    """Classify exact-head release preconditions; missing evidence never passes."""
    if not SHA_PATTERN.fullmatch(sha):
        raise ValueError("source SHA must be 40 lowercase hex digits")
    blocking: list[str] = []
    waiting: list[str] = []
    observed: dict[str, str] = {}
    commit = branch.get("commit")
    branch_sha = commit.get("sha") if isinstance(commit, dict) else None
    if branch.get("name") != branch_name or branch_sha != sha:
        blocking.append("requested release SHA is not current " + branch_name + " HEAD")
    if branch.get("protected") is not True:
        blocking.append("GitHub branch protection is not enabled")
    protection = branch.get("protection")
    status = protection.get("required_status_checks") if isinstance(protection, dict) else None
    checks = status.get("checks") if isinstance(status, dict) else None
    if not isinstance(checks, list) or not any(
        isinstance(c, dict)
        and c.get("context") == REQUIRED_CHECK
        and c.get("app_id") == GITHUB_ACTIONS_APP_ID
        for c in checks
    ):
        blocking.append("required Merge Readiness context/app binding is not verifiable")
    if not isinstance(workflow_runs, list):
        raise ValueError("GitHub workflow inventory was not a list")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in workflow_runs:
        if not isinstance(item, dict):
            raise ValueError("GitHub workflow inventory contains an invalid row")
        if (item.get("head_sha") != sha or item.get("head_branch") != branch_name
                or item.get("event") != "push"):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            grouped.setdefault(name, []).append(item)
    for name in (*REQUIRED_PUSH, *PATH_SCOPED):
        records = grouped.get(name, [])
        if not records:
            if name in REQUIRED_PUSH:
                waiting.append(name + ": exact-head push run missing")
                observed[name] = "missing"
            else:
                observed[name] = "not-triggered (path-scoped)"
            continue
        states: list[str] = []
        for item in records:
            if not isinstance(item.get("id"), int) or item["id"] <= 0:
                blocking.append(name + ": malformed workflow identity")
                states.append("invalid")
                continue
            result = item.get("conclusion")
            state = item.get("status")
            if state != "completed":
                waiting.append(name + ": run " + str(item["id"]) + " not completed")
                states.append("pending")
            elif result != "success":
                blocking.append(name + ": run " + str(item["id"]) + " ended " + str(result))
                states.append("failed")
            else:
                states.append("success")
        # A later green rerun cannot erase a failed run of the same source SHA.
        observed[name] = (
            "failed" if any(s in ("failed", "invalid") for s in states)
            else "pending" if "pending" in states else "success"
        )
    verdict = "BLOCKED" if blocking else "PENDING" if waiting else "READY"
    return {
        "verdict": verdict,
        "branch": branch_name,
        "sha": sha,
        "required_push": list(REQUIRED_PUSH),
        "workflow_results": observed,
        "blocking": blocking,
        "waiting": waiting,
        "production_deployment_attested": False,
    }


def collect(repo: str, sha: str, branch: str, get: Callable[[str], Any] = gh_get) -> dict[str, Any]:
    if not REPO_PATTERN.fullmatch(repo) or not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        raise ValueError("invalid repository or branch argument")
    if not SHA_PATTERN.fullmatch(sha):
        raise ValueError("invalid source SHA")
    path = "/repos/" + repo
    branch_info = get(path + "/branches/" + branch)
    if not isinstance(branch_info, dict):
        raise ValueError("branch metadata is not a JSON object")
    data = get(path + "/actions/runs?head_sha=" + sha + "&per_page=100")
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise ValueError("workflow inventory is missing")
    count = data.get("total_count")
    if not isinstance(count, int) or count > len(data["workflow_runs"]) or count < 0:
        raise ValueError("workflow inventory is truncated; no release certification")
    return assess(sha, branch_info, data["workflow_runs"], branch_name=branch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    try:
        report = collect(args.repo, args.sha, args.branch)
    except ValueError as exc:
        print("release governance verification refused: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"READY": 0, "BLOCKED": 1, "PENDING": 3}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
