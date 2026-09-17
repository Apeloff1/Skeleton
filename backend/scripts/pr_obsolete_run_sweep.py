"""Reconcile obsolete live PR workflow runs that missed lifecycle cleanup.

This trusted default-branch sweep is intentionally conservative: it only
considers ``pull_request``/``dynamic`` runs from the same repository, never
selects the default branch, and preserves any run that cannot be associated
with a PR unambiguously enough to prove it obsolete.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

if __package__:
    from .pr_obsolete_run_drain import (
        LIVE_STATUSES,
        PR_RUN_EVENTS,
        CancelResult,
        GitHubApi,
        cancel_run,
        list_runs,
    )
else:
    from pr_obsolete_run_drain import (
        LIVE_STATUSES,
        PR_RUN_EVENTS,
        CancelResult,
        GitHubApi,
        cancel_run,
        list_runs,
    )


def _repo_full_name(obj: Any) -> str:
    return str((obj or {}).get("full_name") or "")


def _explicit_pr_numbers(run: dict[str, Any]) -> set[int]:
    numbers: set[int] = set()
    for pull in run.get("pull_requests") or []:
        if isinstance(pull, dict):
            number = int(pull.get("number") or 0)
            if number > 0:
                numbers.add(number)
    return numbers


def _commit_pr_numbers(api: GitHubApi, *, repo: str, sha: str, cache: dict[str, set[int]]) -> set[int]:
    if sha in cache:
        return cache[sha]
    quoted_sha = urllib.parse.quote(sha, safe="")
    status, payload, _ = api.request(f"/repos/{repo}/commits/{quoted_sha}/pulls")
    if status != 200 or not isinstance(payload, list):
        raise RuntimeError(f"failed to resolve PR associations for {sha}: HTTP {status}")
    numbers = {int(item.get("number") or 0) for item in payload if isinstance(item, dict) and int(item.get("number") or 0) > 0}
    cache[sha] = numbers
    return numbers


def _fetch_pr(api: GitHubApi, *, repo: str, number: int, cache: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    if cache is not None and number in cache:
        return cache[number]
    status, payload, _ = api.request(f"/repos/{repo}/pulls/{number}")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to resolve PR #{number}: HTTP {status}")
    if cache is not None:
        cache[number] = payload
    return payload


def _matches_run_identity(pr: dict[str, Any], *, repo: str, branch: str, default_branch: str) -> bool:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    return int(pr.get("number") or 0) > 0 and _repo_full_name(head.get("repo")) == repo and str(head.get("ref") or "") == branch and str(base.get("ref") or "") == default_branch


def _candidate_state(candidates: list[dict[str, Any]], *, run_sha: str) -> tuple[bool, bool]:
    for pr in candidates:
        state = str(pr.get("state") or "")
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        if state == "open":
            if not head_sha:
                return True, False
            if head_sha == run_sha:
                return False, True
        elif state != "closed":
            return True, False
    return False, False


def _fresh_candidates(api: GitHubApi, *, repo: str, run: dict[str, Any], branch: str, sha: str, default_branch: str) -> list[dict[str, Any]]:
    numbers = _explicit_pr_numbers(run)
    numbers.update(_commit_pr_numbers(api, repo=repo, sha=sha, cache={}))
    if not numbers:
        return []
    candidates = [_fetch_pr(api, repo=repo, number=n, cache=None) for n in sorted(numbers)]
    return [pr for pr in candidates if _matches_run_identity(pr, repo=repo, branch=branch, default_branch=default_branch)]


def _cancel_for_sweep(api: GitHubApi, repo: str, run_id: int) -> CancelResult:
    """Classify provider-stuck 409/422 as retryable only for periodic sweeps."""
    result = cancel_run(api, repo, run_id)
    if result.outcome == "failed" and result.status in {409, 422}:
        return CancelResult("deferred", result.status)
    return result


def sweep(api: GitHubApi, *, repo: str, current_run_id: int, default_branch: str, max_cancellations: int = 250) -> dict[str, int]:
    if not repo or not default_branch:
        raise RuntimeError("missing sweep repository/default-branch identity")
    if max_cancellations < 1:
        raise RuntimeError("max_cancellations must be positive")
    keys = ("live_seen", "eligible", "authoritative", "unclassified", "resolution_failed", "obsolete", "race_preserved", "over_cap", "accepted", "forced", "moved", "deferred", "failed")
    counts = {key: 0 for key in keys}
    seen_ids: set[int] = set()
    commit_pr_cache: dict[str, set[int]] = {}
    pr_cache: dict[int, dict[str, Any]] = {}
    for status_name in LIVE_STATUSES:
        for run in list_runs(api, repo, status_name):
            run_id = int(run.get("id") or 0)
            if not run_id or run_id in seen_ids:
                continue
            seen_ids.add(run_id)
            counts["live_seen"] += 1
            if run_id == current_run_id or run.get("event") not in PR_RUN_EVENTS:
                continue
            branch = str(run.get("head_branch") or "")
            sha = str(run.get("head_sha") or "")
            if not branch or not sha or branch == default_branch or _repo_full_name(run.get("head_repository")) != repo:
                continue
            counts["eligible"] += 1
            try:
                numbers = _explicit_pr_numbers(run) or _commit_pr_numbers(api, repo=repo, sha=sha, cache=commit_pr_cache)
                if not numbers:
                    counts["unclassified"] += 1
                    continue
                candidates = [_fetch_pr(api, repo=repo, number=n, cache=pr_cache) for n in sorted(numbers)]
            except RuntimeError as exc:
                counts["resolution_failed"] += 1
                print(f"sweep preserve: run={run_id} reason={exc}")
                continue
            candidates = [pr for pr in candidates if _matches_run_identity(pr, repo=repo, branch=branch, default_branch=default_branch)]
            if not candidates:
                counts["unclassified"] += 1
                continue
            unknown, authoritative = _candidate_state(candidates, run_sha=sha)
            if unknown:
                counts["unclassified"] += 1
                continue
            if authoritative:
                counts["authoritative"] += 1
                continue
            counts["obsolete"] += 1
            attempted = sum(counts[key] for key in ("accepted", "forced", "moved", "deferred", "failed"))
            if attempted >= max_cancellations:
                counts["over_cap"] += 1
                continue
            try:
                fresh = _fresh_candidates(api, repo=repo, run=run, branch=branch, sha=sha, default_branch=default_branch)
            except RuntimeError as exc:
                counts["resolution_failed"] += 1
                counts["race_preserved"] += 1
                print(f"sweep preserve before cancel: run={run_id} reason={exc}")
                continue
            if not fresh:
                counts["unclassified"] += 1
                counts["race_preserved"] += 1
                continue
            fresh_unknown, fresh_authoritative = _candidate_state(fresh, run_sha=sha)
            if fresh_unknown:
                counts["unclassified"] += 1
                counts["race_preserved"] += 1
                continue
            if fresh_authoritative:
                counts["authoritative"] += 1
                counts["race_preserved"] += 1
                continue
            result = _cancel_for_sweep(api, repo, run_id)
            counts[result.outcome] += 1
            if result.outcome in {"failed", "deferred"}:
                print(f"sweep cancel {result.outcome}: run={run_id} status={result.status}")
    return counts


def _write_summary(summary: dict[str, int]) -> None:
    text = (
        "## PR Actions backlog sweep\n"
        f"- Live runs seen: {summary['live_seen']}\n"
        f"- Same-repository PR/dynamic candidates: {summary['eligible']}\n"
        f"- Current authoritative runs preserved: {summary['authoritative']}\n"
        f"- Unclassified runs preserved: {summary['unclassified']}\n"
        f"- Association/API resolution failures preserved: {summary['resolution_failed']}\n"
        f"- Initially obsolete runs proven: {summary['obsolete']}\n"
        f"- Runs preserved by pre-cancel live revalidation: {summary['race_preserved']}\n"
        f"- Obsolete runs deferred by sweep cap: {summary['over_cap']}\n"
        f"- Cancel requests accepted: {summary['accepted']}\n"
        f"- Force-cancel requests accepted: {summary['forced']}\n"
        f"- Already completed/moved: {summary['moved']}\n"
        f"- Provider-stuck cancellations deferred: {summary['deferred']}\n"
        f"- Terminal cancellation failures: {summary['failed']}\n"
        "- Trust boundary: only trusted default-branch code executes; default-branch, cross-repository, and unclassified runs are preserved.\n"
    )
    print(" ".join(line.strip() for line in text.splitlines() if line.strip()))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    api = GitHubApi(os.environ["GH_TOKEN"])
    try:
        summary = sweep(api, repo=os.environ["REPO"], current_run_id=int(os.environ["CURRENT_RUN_ID"]), default_branch=os.environ["DEFAULT_BRANCH"], max_cancellations=int(os.environ.get("MAX_CANCELLATIONS") or "250"))
    except RuntimeError as exc:
        print(f"sweep failed: {exc}")
        return 1
    _write_summary(summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
