#!/usr/bin/env python3
"""Read-only merge-readiness reporter for a pull request, ref, or commit (#127).

Produces one deterministic verdict from ``.github/ci/required-checks.json``:

* ``READY``     every required check and lane succeeded on the exact head SHA
                (and, for a PR, it is open, non-draft, and has no conflicts);
* ``PENDING``   nothing has failed yet but a required check is queued, running,
                or not yet created;
* ``NOT_READY`` a required check failed/was cancelled/skipped, or the PR is a
                draft, closed, or conflicting.

It also reports whether branch protection on the policy branch really enforces
the required check. Missing admin visibility is reported as ``unknown`` rather
than guessed.

Uses the caller's ``gh`` authentication through ``gh api`` GET requests only.
Exit codes: 0 READY, 1 NOT_READY, 3 PENDING, 2 usage or API error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / ".github" / "ci" / "required-checks.json"
DEFAULT_REPO = "Apeloff1/Skeleton"
READY, NOT_READY, PENDING = "READY", "NOT_READY", "PENDING"
EXIT_CODES = {READY: 0, NOT_READY: 1, PENDING: 3}
FAILING_CONCLUSIONS = frozenset(
    {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
        "skipped",
    }
)
PASSING_CONCLUSIONS = frozenset({"success"})
NEUTRAL_CONCLUSIONS = frozenset({"neutral"})
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

ApiGet = Callable[[str], Any]


class ApiError(RuntimeError):
    def __init__(self, path: str, status: int | None, message: str) -> None:
        super().__init__(
            f"GET {path} failed ({status if status is not None else 'error'}): {message}"
        )
        self.path = path
        self.status = status


def gh_api_get(path: str) -> Any:
    """GET one REST path through ``gh api`` and decode the JSON body."""

    proc = subprocess.run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "--method",
            "GET",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        status = None
        match = re.search(r"\(HTTP (\d{3})\)", proc.stderr)
        if match:
            status = int(match.group(1))
        raise ApiError(path, status, (proc.stderr or proc.stdout).strip()[:300])
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise ApiError(path, None, f"invalid JSON: {exc}") from exc


@dataclass(frozen=True)
class CheckState:
    name: str
    state: str  # success | failure | pending | missing | neutral
    detail: str
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "detail": self.detail,
            "url": self.url,
        }


def _run_sort_key(run: dict[str, Any]) -> tuple[str, int]:
    return (str(run.get("started_at") or ""), int(run.get("id") or 0))


def classify_run(
    name: str, runs: Iterable[dict[str, Any]], app_id: int | None
) -> CheckState:
    """Classify the newest check run for ``name`` (optionally from one GitHub App)."""

    matching = [
        run
        for run in runs
        if run.get("name") == name
        and (app_id is None or (run.get("app") or {}).get("id") == app_id)
    ]
    if not matching:
        return CheckState(name, "missing", "no check run for this head SHA")
    # Take the newest attempt per check suite, then let the worst suite win so
    # an unrelated workflow job with the same name can never mask a failure.
    per_suite: dict[Any, dict[str, Any]] = {}
    for run in matching:
        suite = (run.get("check_suite") or {}).get("id")
        if suite not in per_suite or _run_sort_key(run) > _run_sort_key(
            per_suite[suite]
        ):
            per_suite[suite] = run
    states = [_classify_one(name, run) for run in per_suite.values()]
    return max(states, key=lambda item: _SEVERITY[item.state])


_SEVERITY = {"success": 0, "neutral": 1, "pending": 2, "failure": 3}


def _classify_one(name: str, latest: dict[str, Any]) -> CheckState:
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    url = latest.get("html_url")
    if status != "completed":
        return CheckState(name, "pending", str(status or "unknown"), url)
    if conclusion in PASSING_CONCLUSIONS:
        return CheckState(name, "success", "success", url)
    if conclusion in NEUTRAL_CONCLUSIONS:
        return CheckState(name, "neutral", "neutral", url)
    if conclusion in FAILING_CONCLUSIONS:
        return CheckState(name, "failure", str(conclusion), url)
    return CheckState(name, "failure", f"unrecognised conclusion {conclusion!r}", url)


def evaluate_protection(
    policy: dict[str, Any], branch: dict[str, Any] | None, protection: Any
) -> dict[str, Any]:
    """Return ``{"state": enforced|not_enforced|mismatch|unknown, "detail": ...}``."""

    if branch is None:
        return {"state": "unknown", "detail": "branch metadata unavailable"}
    if branch.get("protected") is not True:
        return {
            "state": "not_enforced",
            "detail": f"{policy['branch']} is not protected",
        }
    if not isinstance(protection, dict):
        return {
            "state": "unknown",
            "detail": "protection details need repository admin visibility",
        }
    check = policy["required_status_checks"][0]
    status = protection.get("required_status_checks") or {}
    checks = status.get("checks") or []
    has_check = any(
        item.get("context") == check["context"]
        and item.get("app_id") == check["app_id"]
        for item in checks
    )
    problems = []
    if not has_check:
        problems.append(
            f"{check['context']!r} from app {check['app_id']} is not required"
        )
    if status.get("strict") is not policy["protection"]["strict"]:
        problems.append("strict up-to-date mode differs from policy")
    if ((protection.get("enforce_admins") or {}).get("enabled")) is not policy[
        "protection"
    ]["enforce_admins"]:
        problems.append("admin enforcement differs from policy")
    if (protection.get("allow_force_pushes") or {}).get("enabled") is not False:
        problems.append("force-pushes are allowed")
    if (protection.get("allow_deletions") or {}).get("enabled") is not False:
        problems.append("branch deletion is allowed")
    if problems:
        return {"state": "mismatch", "detail": "; ".join(problems)}
    return {
        "state": "enforced",
        "detail": f"{check['context']} is required with the policy settings",
    }


def evaluate(
    policy: dict[str, Any],
    sha: str,
    check_runs: list[dict[str, Any]],
    pull: dict[str, Any] | None = None,
    protection_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure verdict function: no I/O, deterministic ordering."""

    required = [
        classify_run(item["context"], check_runs, item["app_id"])
        for item in policy["required_status_checks"]
    ]
    actions_app = policy["required_status_checks"][0]["app_id"]
    lanes = [
        classify_run(lane["name"], check_runs, actions_app)
        for lane in policy["aggregate_lanes"]
    ]
    blockers: list[str] = []
    waiting: list[str] = []
    for item in required + lanes:
        if item.state in {"failure", "neutral"}:
            blockers.append(f"{item.name}: {item.detail}")
        elif item.state in {"pending", "missing"}:
            waiting.append(f"{item.name}: {item.detail}")
    pr_summary = None
    if pull is not None:
        head_sha = (pull.get("head") or {}).get("sha")
        pr_summary = {
            "number": pull.get("number"),
            "title": pull.get("title"),
            "state": pull.get("state"),
            "draft": bool(pull.get("draft")),
            "base": (pull.get("base") or {}).get("ref"),
            "head_ref": (pull.get("head") or {}).get("ref"),
            "mergeable": pull.get("mergeable"),
            "mergeable_state": pull.get("mergeable_state"),
        }
        if head_sha and head_sha != sha:
            blockers.append(
                f"PR head moved to {head_sha}; evidence for {sha} is historical"
            )
        if pull.get("state") != "open":
            blockers.append(f"PR is {pull.get('state')}")
        if pull.get("draft"):
            blockers.append("PR is a draft")
        if pr_summary["base"] != policy["branch"]:
            blockers.append(
                f"PR targets {pr_summary['base']!r}, not {policy['branch']!r}"
            )
        if pull.get("mergeable") is False or pull.get("mergeable_state") == "dirty":
            blockers.append("PR has merge conflicts")
        elif pull.get("mergeable") is None:
            waiting.append("GitHub is still computing mergeability")
        if pull.get("mergeable_state") == "behind":
            waiting.append("PR branch is behind base; update it before merging")
    if blockers:
        verdict = NOT_READY
    elif waiting:
        verdict = PENDING
    else:
        verdict = READY
    return {
        "schema_version": 1,
        "verdict": verdict,
        "sha": sha,
        "branch": policy["branch"],
        "required_checks": [item.as_dict() for item in required],
        "lanes": [item.as_dict() for item in lanes],
        "pull_request": pr_summary,
        "protection": protection_state or {"state": "unknown", "detail": "not queried"},
        "blockers": blockers,
        "waiting": waiting,
    }


def fetch_check_runs(
    api_get: ApiGet, repo: str, sha: str, max_pages: int = 30
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        body = api_get(
            f"repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}"
        )
        batch = (body or {}).get("check_runs") or []
        runs.extend(batch)
        total = int((body or {}).get("total_count") or 0)
        if len(batch) < 100 or len(runs) >= total:
            break
    return runs


def fetch_protection(
    api_get: ApiGet, repo: str, policy: dict[str, Any]
) -> dict[str, Any]:
    branch_name = policy["branch"]
    try:
        branch = api_get(f"repos/{repo}/branches/{branch_name}")
    except ApiError as exc:
        return {"state": "unknown", "detail": str(exc)}
    protection: Any = None
    if isinstance(branch, dict) and branch.get("protected") is True:
        try:
            protection = api_get(f"repos/{repo}/branches/{branch_name}/protection")
        except ApiError as exc:
            if exc.status not in (403, 404):
                return {"state": "unknown", "detail": str(exc)}
    return evaluate_protection(
        policy, branch if isinstance(branch, dict) else None, protection
    )


def collect(
    policy: dict[str, Any],
    repo: str,
    *,
    pr: int | None = None,
    sha: str | None = None,
    ref: str | None = None,
    api_get: ApiGet = gh_api_get,
    include_protection: bool = True,
) -> dict[str, Any]:
    pull = None
    if pr is not None:
        pull = api_get(f"repos/{repo}/pulls/{pr}")
        sha = (pull.get("head") or {}).get("sha")
    elif ref is not None:
        sha = (api_get(f"repos/{repo}/commits/{ref}") or {}).get("sha")
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        raise ApiError(
            "resolve head", None, f"could not resolve a full commit SHA (got {sha!r})"
        )
    runs = fetch_check_runs(api_get, repo, sha)
    protection = fetch_protection(api_get, repo, policy) if include_protection else None
    report = evaluate(policy, sha, runs, pull, protection)
    report["repo"] = repo
    return report


def render_text(report: dict[str, Any]) -> str:
    symbols = {
        "success": "PASS",
        "failure": "FAIL",
        "pending": "WAIT",
        "missing": "MISS",
        "neutral": "NEUT",
    }
    lines = [
        f"Merge readiness for {report.get('repo', '?')}@{report['sha'][:12]}: {report['verdict']}"
    ]
    pr = report.get("pull_request")
    if pr:
        lines.append(
            f"  PR #{pr['number']} {pr['head_ref']} -> {pr['base']} state={pr['state']} draft={pr['draft']} "
            f"mergeable={pr['mergeable']} ({pr['mergeable_state']})"
        )
    lines.append("  Required checks:")
    for item in report["required_checks"]:
        lines.append(
            f"    [{symbols[item['state']]}] {item['name']} — {item['detail']}"
        )
    lines.append("  Lanes:")
    for item in report["lanes"]:
        lines.append(
            f"    [{symbols[item['state']]}] {item['name']} — {item['detail']}"
        )
    protection = report["protection"]
    lines.append(
        f"  Branch protection ({report['branch']}): {protection['state']} — {protection['detail']}"
    )
    for label in ("blockers", "waiting"):
        if report[label]:
            lines.append(f"  {label.capitalize()}:")
            lines.extend(f"    - {item}" for item in report[label])
    return "\n".join(lines)


def main(argv: list[str] | None = None, api_get: ApiGet = gh_api_get) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int, help="pull request number")
    target.add_argument("--sha", help="full 40-character commit SHA")
    target.add_argument("--ref", help="branch or tag name, e.g. main")
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"owner/name (default {DEFAULT_REPO})"
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--no-protection", action="store_true", help="skip the branch-protection query"
    )
    args = parser.parse_args(argv)
    if not _REPO_RE.match(args.repo):
        parser.error("--repo must be owner/name")
    if args.sha is not None and not _SHA_RE.match(args.sha):
        parser.error("--sha must be a full lowercase 40-character SHA")
    if args.ref is not None and (not _REF_RE.match(args.ref) or ".." in args.ref):
        parser.error("--ref contains unsupported characters")
    if args.pr is not None and args.pr <= 0:
        parser.error("--pr must be positive")
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        report = collect(
            policy,
            args.repo,
            pr=args.pr,
            sha=args.sha,
            ref=args.ref,
            api_get=api_get,
            include_protection=not args.no_protection,
        )
    except (OSError, ValueError, KeyError, ApiError) as exc:
        print(f"merge-readiness-status: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else render_text(report)
    )
    return EXIT_CODES[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
