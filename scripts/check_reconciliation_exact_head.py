#!/usr/bin/env python3
"""Fail-closed structural verification for a complete stacked PR CI evidence bundle.

This module does not query GitHub or authenticate submitted JSON. A structurally
valid bundle is *never* merge, security, device, model, release, or owner approval.
The source of truth remains live GitHub at the final exact SHA of every PR.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "machine" / "draft19_reconciliation.json"
SCHEMA = "skeleton.reconciliation.head-checks.v1"
REPO = "Apeloff1/Skeleton"
CHAIN = (5074, 5081, 5089)
SHA = re.compile(r"[a-f0-9]{40}\Z")
MAX_BYTES = 1024 * 1024
MAX_WORKFLOWS = 100
MAX_JOBS = 300
REQUIRED_MERGE_JOBS = frozenset(
    {f"Canonical Domain Suite ({i})" for i in range(8)}
    | {"PR Automation Tests", "Lint Type Security",
       "Quarantine Policy", "Integration Smoke"}
)
MANDATORY_GATES = frozenset({
    "Merge Readiness", "Backend Quality", "App Foundation E2E",
    "Malware Gate", "Artifact Policy", "Repository Hygiene Gate",
    "Secret scanning", "Dependency Review", "Workflow Input Security",
    "Sealed Context Guard",
})
EXTRA_WORKFLOWS = frozenset({
    "Jeeves integrated mirror and local-AI CI qualification",
    "Jeeves native SQLite source qualification",
    "Draft19 GGUF and source custody qualification",
})


class EvidenceHold(ValueError):
    """An evidence bundle is unqualified or malformed."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceHold(reason)


def pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON field")
        out[key] = value
    return out


def parse(raw: bytes) -> dict[str, Any]:
    require(type(raw) is bytes and 1 <= len(raw) <= MAX_BYTES,
            "missing or oversized evidence")
    try:
        parsed = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs_no_duplicates,
            parse_constant=lambda _v: (_ for _ in ()).throw(
                EvidenceHold("nonfinite JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceHold("invalid evidence JSON") from exc
    require(type(parsed) is dict, "evidence must be an object")
    return parsed


def check_sha(value: Any, label: str) -> str:
    require(type(value) is str and SHA.fullmatch(value) is not None,
            f"invalid {label} SHA")
    return value


def read_required_workflows(path: Path = POLICY) -> frozenset[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=pairs_no_duplicates)
    except (OSError, ValueError, UnicodeError) as exc:
        raise EvidenceHold("missing or corrupt checked-in gate policy") from exc
    require(type(data) is dict
            and data.get("schema") == "draft19-reconciliation/v1"
            and data.get("owner") == REPO
            and data.get("admission") == "review_only"
            and data.get("merge_approved") is False
            and data.get("release_approved") is False,
            "gate policy is not a held source-review policy")
    names = data.get("required_gates")
    require(type(names) is list and len(names) >= 10
            and all(type(name) is str and name.strip() == name and name
                    for name in names)
            and len(names) == len(set(names)), "invalid required gate inventory")
    require(MANDATORY_GATES.issubset(names),
            "mandatory gate omitted from policy")
    return frozenset(names)


def check_job(job: Any, sha: str, workflow: str) -> str:
    require(type(job) is dict
            and set(job) == {"name", "head_sha", "status", "conclusion"},
            f"invalid {workflow} job schema")
    name = job["name"]
    require(type(name) is str and 1 <= len(name) <= 200
            and name.strip() == name, "invalid job name")
    require(check_sha(job["head_sha"], "job head") == sha,
            f"ancestor job evidence: {workflow}/{name}")
    require(job["status"] == "completed"
            and job["conclusion"] == "success",
            f"pending, skipped, cancelled or failed job: {workflow}/{name}")
    return name


def check_workflow(entry: Any, sha: str) -> str:
    require(type(entry) is dict
            and set(entry) == {"name", "head_sha", "status", "conclusion",
                               "run_id", "run_attempt", "jobs"},
            "invalid workflow schema")
    name = entry["name"]
    require(type(name) is str and 1 <= len(name) <= 200
            and name.strip() == name, "invalid workflow name")
    require(check_sha(entry["head_sha"], "workflow head") == sha,
            f"ancestor workflow evidence: {name}")
    require(type(entry["run_id"]) is int and 1 <= entry["run_id"] < 10**16,
            "invalid workflow run identity")
    require(type(entry["run_attempt"]) is int
            and 1 <= entry["run_attempt"] <= 1000,
            "invalid run attempt identity")
    require(entry["status"] == "completed"
            and entry["conclusion"] == "success",
            f"queued, skipped, cancelled or failed workflow: {name}")
    jobs = entry["jobs"]
    require(type(jobs) is list and 1 <= len(jobs) <= MAX_JOBS,
            f"missing or oversized workflow jobs: {name}")
    seen: set[str] = set()
    for job in jobs:
        job_name = check_job(job, sha, name)
        require(job_name not in seen, f"duplicate job: {name}/{job_name}")
        seen.add(job_name)
    if name == "Merge Readiness":
        missing = sorted(REQUIRED_MERGE_JOBS - seen)
        require(not missing,
                "missing canonical or security merge jobs: " + ", ".join(missing))
    return name


def validate(data: Any, required: frozenset[str] | None = None) -> dict[str, Any]:
    """Validate exact SHA and all gates; NEVER provide release authorization.

    This checks internal consistency only, not the authenticity of an export.
    """
    require(type(data) is dict
            and set(data) == {"schema", "repository", "source",
                              "admission", "merge_authorized",
                              "release_authorized", "pr_chain"},
            "invalid top-level evidence schema")
    require(data["schema"] == SCHEMA and data["repository"] == REPO
            and data["source"] == "github_api_export_review_only"
            and data["admission"] == "review_only"
            and data["merge_authorized"] is False
            and data["release_authorized"] is False,
            "fabricated evidence provenance or authority")
    rows = data["pr_chain"]
    require(type(rows) is list and len(rows) == len(CHAIN),
            "complete three-PR dependency chain required")
    required = read_required_workflows() if required is None else required
    require(type(required) is frozenset and len(required) >= 10
            and MANDATORY_GATES.issubset(required),
            "untrusted gate policy")
    seen_heads: set[str] = set()
    previous: str | None = None
    summary: dict[int, str] = {}
    for index, row in enumerate(rows):
        require(type(row) is dict
                and set(row) == {"number", "head_sha", "base_head_sha",
                                 "draft", "merged", "workflows"},
                "invalid PR evidence schema")
        number = CHAIN[index]
        require(type(row["number"]) is int and row["number"] == number,
                "PR chain reordered, missing or replaced")
        require(row["merged"] is False, "merged PR is not a held review")
        require(type(row["draft"]) is bool, "PR draft status must be boolean")
        head = check_sha(row["head_sha"], "PR head")
        base = check_sha(row["base_head_sha"], "PR base")
        require(head not in seen_heads and head != base,
                "cyclic or repeated source head")
        seen_heads.add(head)
        if previous is not None:
            require(base == previous,
                    f"stale ancestor for PR #{number}: recheck parent head")
        previous = head
        workflows = row["workflows"]
        require(type(workflows) is list
                and 1 <= len(workflows) <= MAX_WORKFLOWS,
                "missing or oversized workflow inventory")
        names: set[str] = set()
        for workflow in workflows:
            name = check_workflow(workflow, head)
            require(name not in names, f"duplicate workflow: {name}")
            names.add(name)
        expected = set(required)
        if number == 5089:
            expected.update(EXTRA_WORKFLOWS)
        missing = sorted(expected - names)
        require(not missing, f"PR #{number} missing workflows: " + ", ".join(missing))
        summary[number] = head
    return {
        "source_check_inventory": "structurally_complete_only",
        "head_shas": {str(k): v for k, v in summary.items()},
        "approval": "denied_without_live_github_and_independent_review",
        "merge_authorized": False,
        "release_authorized": False,
        "native_or_device_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True,
                        help="Locally captured, read-only GitHub API evidence bundle")
    args = parser.parse_args(argv)
    try:
        result = validate(parse(args.evidence.read_bytes()))
    except (OSError, EvidenceHold) as exc:
        print(f"RECONCILIATION_HOLD: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
