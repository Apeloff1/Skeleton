"""Reconcile obsolete live PR workflow runs that missed lifecycle cleanup.

This trusted default-branch sweep is intentionally conservative: it only
considers ``pull_request``/``dynamic`` runs from the same repository, never
selects the default branch, and preserves any run that cannot be associated
with a PR unambiguously enough to prove it obsolete.
"""

from __future__ import annotations

import os
from typing import Any

if __package__:
    from .pr_obsolete_run_drain import (
        LIVE_STATUSES,
        PR_RUN_EVENTS,
        CancelResult,
        GitHubApi,
        cancel_run,
        canonical_commit_oid,
        list_commit_associated_pulls,
        list_runs,
    )
else:
    from pr_obsolete_run_drain import (
        LIVE_STATUSES,
        PR_RUN_EVENTS,
        CancelResult,
        GitHubApi,
        cancel_run,
        canonical_commit_oid,
        list_commit_associated_pulls,
        list_runs,
    )


def _repo_full_name(obj: Any) -> str:
    return str((obj or {}).get("full_name") or "")


def _explicit_pr_numbers(run: dict[str, Any]) -> set[int]:
    numbers: set[int] = set()
    for pull in run.get("pull_requests") or []:
        if not isinstance(pull, dict):
            continue
        number = int(pull.get("number") or 0)
        if number > 0:
            numbers.add(number)
    return numbers


def _commit_pr_numbers(
    api: GitHubApi,
    *,
    repo: str,
    sha: str,
    cache: dict[str, set[int]],
) -> set[int]:
    sha = canonical_commit_oid(sha)
    if sha in cache:
        return cache[sha]
    numbers = {
        int(item.get("number") or 0)
        for item in list_commit_associated_pulls(api, repo, sha)
        if int(item.get("number") or 0) > 0
    }
    cache[sha] = numbers
    return numbers


def _fetch_pr(
    api: GitHubApi,
    *,
    repo: str,
    number: int,
    cache: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if cache is not None and number in cache:
        return cache[number]
    status, payload, _ = api.request(f"/repos/{repo}/pulls/{number}")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to resolve PR #{number}: HTTP {status}")
    if cache is not None:
        cache[number] = payload
    return payload


def _matches_run_identity(
    pr: dict[str, Any],
    *,
    repo: str,
    branch: str,
    default_branch: str,
) -> bool:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    return (
        int(pr.get("number") or 0) > 0
        and _repo_full_name(head.get("repo")) == repo
        and str(head.get("ref") or "") == branch
        and str(base.get("ref") or "") == default_branch
    )


def _candidate_state(
    candidates: list[dict[str, Any]], *, run_sha: str
) -> tuple[bool, bool]:
    """Return (unknown, authoritative) for matching PR candidates."""
    unknown = False
    authoritative = False
    for pr in candidates:
        state = str(pr.get("state") or "")
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        if state == "open":
            if not head_sha:
                unknown = True
                break
            try:
                live_sha = canonical_commit_oid(head_sha)
            except RuntimeError:
                unknown = True
                break
            if live_sha == run_sha:
                authoritative = True
                break
        elif state != "closed":
            unknown = True
            break
    return unknown, authoritative


def _fresh_candidates(
    api: GitHubApi,
    *,
    repo: str,
    run: dict[str, Any],
    branch: str,
    sha: str,
    default_branch: str,
) -> list[dict[str, Any]]:
    """Re-resolve associations and PR state immediately before mutation.

    This intentionally bypasses the scan caches: a PR can reopen or an open PR
    can move its head back to the run SHA after the first classification pass.
    Cancellation authority must therefore be based on a fresh live read.
    """
    numbers = _explicit_pr_numbers(run)
    numbers.update(
        _commit_pr_numbers(
            api,
            repo=repo,
            sha=sha,
            cache={},
        )
    )
    if not numbers:
        return []

    candidates = [
        _fetch_pr(api, repo=repo, number=number, cache=None)
        for number in sorted(numbers)
    ]
    return [
        pr
        for pr in candidates
        if _matches_run_identity(
            pr,
            repo=repo,
            branch=branch,
            default_branch=default_branch,
        )
    ]


def _cancel_for_sweep(api: GitHubApi, repo: str, run_id: int) -> CancelResult:
    """Treat provider-stuck cancel conflicts as retryable only in the sweep."""
    result = cancel_run(api, repo, run_id)
    if result.outcome == "failed" and result.status in {409, 422}:
        return CancelResult("deferred", result.status)
    return result


def sweep(
    api: GitHubApi,
    *,
    repo: str,
    current_run_id: int,
    default_branch: str,
    max_cancellations: int = 250,
) -> dict[str, int]:
    if not repo or not default_branch:
        raise RuntimeError("missing sweep repository/default-branch identity")
    if max_cancellations < 1:
        raise RuntimeError("max_cancellations must be positive")

    counts = {
        "live_seen": 0,
        "eligible": 0,
        "authoritative": 0,
        "unclassified": 0,
        "resolution_failed": 0,
        "obsolete": 0,
        "race_preserved": 0,
        "over_cap": 0,
        "accepted": 0,
        "forced": 0,
        "moved": 0,
        "deferred": 0,
        "failed": 0,
    }
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
            raw_sha = str(run.get("head_sha") or "")
            run_repo = _repo_full_name(run.get("head_repository"))
            if (
                not branch
                or not raw_sha
                or branch == default_branch
                or run_repo != repo
            ):
                continue
            try:
                sha = canonical_commit_oid(raw_sha)
            except RuntimeError:
                continue
            counts["eligible"] += 1

            try:
                numbers = _explicit_pr_numbers(run)
                if not numbers:
                    numbers = _commit_pr_numbers(
                        api,
                        repo=repo,
                        sha=sha,
                        cache=commit_pr_cache,
                    )
                if not numbers:
                    counts["unclassified"] += 1
                    continue

                candidates = [
                    _fetch_pr(api, repo=repo, number=number, cache=pr_cache)
                    for number in sorted(numbers)
                ]
            except RuntimeError as exc:
                if "bounded identity scan" in str(exc):
                    raise
                counts["resolution_failed"] += 1
                print(f"sweep preserve: run={run_id} reason={exc}")
                continue

            candidates = [
                pr
                for pr in candidates
                if _matches_run_identity(
                    pr,
                    repo=repo,
                    branch=branch,
                    default_branch=default_branch,
                )
            ]
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
            attempted = (
                counts["accepted"]
                + counts["forced"]
                + counts["moved"]
                + counts["deferred"]
                + counts["failed"]
            )
            if attempted >= max_cancellations:
                counts["over_cap"] += 1
                continue

            # The scan above can be minutes old in a large backlog. Re-resolve
            # both commit associations and PR state immediately before mutation.
            try:
                fresh = _fresh_candidates(
                    api,
                    repo=repo,
                    run=run,
                    branch=branch,
                    sha=sha,
                    default_branch=default_branch,
                )
            except RuntimeError as exc:
                if "bounded identity scan" in str(exc):
                    raise
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
            if result.outcome == "failed":
                print(f"sweep cancel failed: run={run_id} status={result.status}")

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
        f"- Transient cancellations deferred: {summary['deferred']}\n"
        f"- Terminal cancellation failures: {summary['failed']}\n"
        "- Trust boundary: only trusted default-branch code executes; "
        "default-branch, cross-repository, and unclassified runs are preserved.\n"
    )
    print(" ".join(line.strip() for line in text.splitlines() if line.strip()))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPO"]
    current_run_id = int(os.environ["CURRENT_RUN_ID"])
    default_branch = os.environ["DEFAULT_BRANCH"]
    max_cancellations = int(os.environ.get("MAX_CANCELLATIONS") or "250")
    api = GitHubApi(token)
    try:
        summary = sweep(
            api,
            repo=repo,
            current_run_id=current_run_id,
            default_branch=default_branch,
            max_cancellations=max_cancellations,
        )
    except RuntimeError as exc:
        print(f"sweep failed: {exc}")
        return 1

    _write_summary(summary)
    if summary["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
