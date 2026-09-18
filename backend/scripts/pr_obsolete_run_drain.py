"""Trusted PR-lifecycle Actions cleanup.

This module is executed only from a pull_request_target workflow that checks out
the event's trusted base SHA. It never imports or executes pull-request code.

The drainer cancels live pull_request/dynamic workflow runs that belong to one
same-repository PR and are no longer authoritative for that PR's current head.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

LIVE_STATUSES = ("queued", "in_progress", "waiting", "pending", "requested")
PR_RUN_EVENTS = frozenset({"pull_request", "dynamic"})
BASE_RETRYABLE = frozenset({0, 429, 500, 502, 503, 504})
COMMIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
COMMIT_PULLS_PAGE_SIZE = 100
MAX_COMMIT_PULLS_PAGES = 10
RUN_PAGE_SIZE = 100
MAX_RUN_PAGES = 10
PR_COMMITS_PAGE_SIZE = 100
MAX_PR_COMMIT_PAGES = 3


@dataclass(frozen=True)
class DrainContext:
    repo: str
    current_run_id: int
    pr_number: int
    event_action: str
    event_head_repo: str
    event_head_ref: str
    event_head_sha: str
    event_before_sha: str
    default_branch: str


@dataclass(frozen=True)
class CancelResult:
    outcome: str
    status: int


class GitHubApi:
    def __init__(self, token: str, *, sleep: Callable[[float], None] = time.sleep):
        self._token = token
        self._sleep = sleep
        self._api = "https://api.github.com"
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "skeleton-pr-run-drainer",
        }

    def request(self, path: str, *, method: str = "GET") -> tuple[int, Any, dict[str, str]]:
        req = urllib.request.Request(
            self._api + path,
            data=b"" if method != "GET" else None,
            headers=self._headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                payload = json.loads(raw) if raw else None
                return response.status, payload, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                payload = json.loads(raw) if raw else None
            except (OSError, ValueError):
                payload = None
            return exc.code, payload, dict(exc.headers.items()) if exc.headers else {}
        except urllib.error.URLError:
            return 0, None, {}

    def sleep(self, seconds: float) -> None:
        self._sleep(seconds)


def _repo_full_name(obj: Any) -> str:
    return str((obj or {}).get("full_name") or "")


def canonical_commit_oid(value: str) -> str:
    """Return a lowercase 40-hex Git commit OID, or fail closed.

    Privileged workflow_run identity must be an immutable full SHA. Whitespace,
    abbreviations, and non-hex values are rejected so they cannot degrade into
    an ambiguous commits/history lookup.
    """
    if not isinstance(value, str):
        raise RuntimeError("workflow_run head SHA must be a 40-character hex commit OID")
    oid = value.casefold()
    if COMMIT_OID_RE.fullmatch(oid) is None:
        raise RuntimeError("workflow_run head SHA must be a 40-character hex commit OID")
    return oid


def list_commit_associated_pulls(api: GitHubApi, repo: str, sha: str) -> list[dict[str, Any]]:
    """Return every PR GitHub associates with a commit, or fail closed.

    ``/commits/{sha}/pulls`` is paginated. A single first page can hide later
    same-head PRs, so identity recovery must scan a bounded complete prefix.
    Abbreviated or malformed SHAs are rejected before lookup.
    """
    if not repo or not sha:
        raise RuntimeError("incomplete commit identity for PR association")
    sha = canonical_commit_oid(sha)
    quoted_sha = urllib.parse.quote(sha, safe="")
    items: list[dict[str, Any]] = []
    for page in range(1, MAX_COMMIT_PULLS_PAGES + 1):
        query = urllib.parse.urlencode(
            {"per_page": COMMIT_PULLS_PAGE_SIZE, "page": page}
        )
        status, payload, _ = api.request(f"/repos/{repo}/commits/{quoted_sha}/pulls?{query}")
        if status != 200 or not isinstance(payload, list):
            raise RuntimeError(
                f"failed to resolve PR associations for {sha}: HTTP {status}"
            )
        items.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < COMMIT_PULLS_PAGE_SIZE:
            return items
    raise RuntimeError("commit PR association exceeded bounded identity scan")


def _retryable(status: int, payload: Any) -> bool:
    if status in BASE_RETRYABLE:
        return True
    if status != 403:
        return False
    message = str((payload or {}).get("message") or "").lower()
    return "rate limit" in message or "abuse" in message


def _retry_delay(headers: dict[str, str], attempt: int) -> float:
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value:
        try:
            return max(0.0, min(float(value), 30.0))
        except ValueError:
            pass
    return float(2 ** attempt)


def list_runs(api: GitHubApi, repo: str, status_name: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for page in range(1, MAX_RUN_PAGES + 1):
        query = urllib.parse.urlencode(
            {"status": status_name, "per_page": RUN_PAGE_SIZE, "page": page}
        )
        status, payload, _ = api.request(f"/repos/{repo}/actions/runs?{query}")
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"failed to list {status_name} runs: HTTP {status}")
        batch = payload.get("workflow_runs") or []
        if not isinstance(batch, list):
            raise RuntimeError(f"malformed {status_name} workflow run payload")
        runs.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < RUN_PAGE_SIZE:
            return runs
    raise RuntimeError(
        f"live {status_name} run listing exceeded bounded identity scan"
    )


def fetch_pr(api: GitHubApi, repo: str, pr_number: int) -> dict[str, Any]:
    status, payload, _ = api.request(f"/repos/{repo}/pulls/{pr_number}")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to resolve PR #{pr_number}: HTTP {status}")
    return payload


def list_pr_commit_shas(api: GitHubApi, repo: str, pr_number: int) -> set[str]:
    shas: set[str] = set()
    # GitHub caps pull-request commits at 250; three 100-entry pages cover it.
    for page in range(1, MAX_PR_COMMIT_PAGES + 1):
        query = urllib.parse.urlencode({"per_page": PR_COMMITS_PAGE_SIZE, "page": page})
        status, payload, _ = api.request(
            f"/repos/{repo}/pulls/{pr_number}/commits?{query}"
        )
        if status != 200 or not isinstance(payload, list):
            raise RuntimeError(f"failed to list PR #{pr_number} commits: HTTP {status}")
        for commit in payload:
            if not isinstance(commit, dict) or not commit.get("sha"):
                continue
            shas.add(canonical_commit_oid(str(commit["sha"])))
        if len(payload) < PR_COMMITS_PAGE_SIZE:
            return shas
    raise RuntimeError(
        f"PR #{pr_number} commit listing exceeded bounded identity scan"
    )


def explicit_pr_link(run: dict[str, Any], pr_number: int) -> bool:
    for pull in run.get("pull_requests") or []:
        if isinstance(pull, dict) and int(pull.get("number") or 0) == pr_number:
            return True
    return False


def commit_links_pr(
    api: GitHubApi,
    repo: str,
    sha: str,
    pr_number: int,
    cache: dict[str, bool],
) -> bool:
    if not sha:
        return False
    try:
        sha = canonical_commit_oid(sha)
    except RuntimeError:
        return False
    if sha in cache:
        return cache[sha]
    pulls = list_commit_associated_pulls(api, repo, sha)
    linked = any(
        isinstance(pull, dict) and int(pull.get("number") or 0) == pr_number
        for pull in pulls
    )
    cache[sha] = linked
    return linked


def belongs_to_pr(
    api: GitHubApi,
    run: dict[str, Any],
    *,
    context: DrainContext,
    pr: dict[str, Any],
    known_pr_shas: set[str],
    commit_link_cache: dict[str, bool],
) -> bool:
    if run.get("event") not in PR_RUN_EVENTS:
        return False

    run_id = int(run.get("id") or 0)
    if not run_id or run_id == context.current_run_id:
        return False

    run_branch = str(run.get("head_branch") or "")
    if not run_branch or run_branch == context.default_branch:
        return False

    if explicit_pr_link(run, context.pr_number):
        return True

    head = pr.get("head") or {}
    pr_head_ref = str(head.get("ref") or context.event_head_ref)
    pr_head_repo = _repo_full_name(head.get("repo")) or context.event_head_repo
    run_head_repo = _repo_full_name(run.get("head_repository"))

    if (
        pr_head_repo != context.repo
        or run_head_repo != context.repo
        or run_branch != pr_head_ref
    ):
        return False

    try:
        sha = canonical_commit_oid(str(run.get("head_sha") or ""))
    except RuntimeError:
        return False
    live_head_sha = str(head.get("sha") or "")
    try:
        live_head_oid = canonical_commit_oid(live_head_sha) if live_head_sha else ""
    except RuntimeError:
        live_head_oid = ""
    trusted_event_shas = {
        value.casefold()
        for value in (
            context.event_head_sha,
            context.event_before_sha,
            live_head_oid,
        )
        if value
    }
    folded_known = {item.casefold() for item in known_pr_shas}
    if sha in trusted_event_shas or sha in folded_known:
        return True

    return commit_links_pr(
        api, context.repo, sha, context.pr_number, commit_link_cache
    )


def _run_completed(api: GitHubApi, repo: str, run_id: int) -> bool:
    status, payload, _ = api.request(f"/repos/{repo}/actions/runs/{run_id}")
    return (
        status == 200
        and isinstance(payload, dict)
        and payload.get("status") == "completed"
    )


def _post_with_retry(
    api: GitHubApi,
    path: str,
    *,
    attempts: int = 3,
) -> tuple[int, Any]:
    status = 0
    payload: Any = None
    for attempt in range(attempts):
        status, payload, headers = api.request(path, method="POST")
        if not _retryable(status, payload):
            return status, payload
        if attempt + 1 < attempts:
            api.sleep(_retry_delay(headers, attempt))
    return status, payload


def cancel_run(api: GitHubApi, repo: str, run_id: int) -> CancelResult:
    status, payload = _post_with_retry(
        api, f"/repos/{repo}/actions/runs/{run_id}/cancel"
    )
    if status in {200, 202}:
        return CancelResult("accepted", status)
    if status == 404:
        return CancelResult("moved", status)
    if status in {409, 422} and _run_completed(api, repo, run_id):
        return CancelResult("moved", status)

    if status in {409, 422} or _retryable(status, payload):
        forced_status, forced_payload = _post_with_retry(
            api, f"/repos/{repo}/actions/runs/{run_id}/force-cancel"
        )
        if forced_status in {200, 202}:
            return CancelResult("forced", forced_status)
        if forced_status == 404:
            return CancelResult("moved", forced_status)
        if forced_status in {409, 422} and _run_completed(api, repo, run_id):
            return CancelResult("moved", forced_status)
        if _retryable(forced_status, forced_payload):
            return CancelResult("deferred", forced_status)
        return CancelResult("failed", forced_status)

    return CancelResult("failed", status)


def build_context_from_env() -> DrainContext:
    before = os.environ.get("EVENT_BEFORE_SHA", "")
    return DrainContext(
        repo=os.environ["REPO"],
        current_run_id=int(os.environ["CURRENT_RUN_ID"]),
        pr_number=int(os.environ["PR_NUMBER"]),
        event_action=os.environ["PR_ACTION"],
        event_head_repo=os.environ["EVENT_HEAD_REPO"],
        event_head_ref=os.environ["EVENT_HEAD_REF"],
        event_head_sha=canonical_commit_oid(os.environ["EVENT_HEAD_SHA"]),
        event_before_sha=canonical_commit_oid(before) if before else "",
        default_branch=os.environ["DEFAULT_BRANCH"],
    )


def drain(api: GitHubApi, context: DrainContext) -> dict[str, int | str]:
    if context.event_action not in {"synchronize", "closed"}:
        raise RuntimeError(
            f"unexpected pull_request_target action: {context.event_action!r}"
        )
    if context.event_head_repo != context.repo:
        raise RuntimeError("refusing privileged cleanup for a cross-repository PR")
    if not context.event_head_ref:
        raise RuntimeError("missing pull-request head ref")
    if context.default_branch == context.event_head_ref:
        raise RuntimeError("refusing PR cleanup whose head is the default branch")

    pr = fetch_pr(api, context.repo, context.pr_number)
    head = pr.get("head") or {}
    live_head_repo = _repo_full_name(head.get("repo"))
    if live_head_repo != context.repo:
        raise RuntimeError("pull request is no longer same-repository")

    state = str(pr.get("state") or "")
    if state == "open":
        authoritative_sha = canonical_commit_oid(str(head.get("sha") or ""))
    else:
        authoritative_sha = ""
    known_pr_shas = list_pr_commit_shas(api, context.repo, context.pr_number)
    known_pr_shas.update(
        value
        for value in (
            context.event_head_sha,
            context.event_before_sha,
            authoritative_sha,
        )
        if value
    )

    inspected = 0
    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    commit_link_cache: dict[str, bool] = {}

    for status_name in LIVE_STATUSES:
        for run in list_runs(api, context.repo, status_name):
            run_id = int(run.get("id") or 0)
            if not run_id or run_id in seen_ids:
                continue
            if not belongs_to_pr(
                api,
                run,
                context=context,
                pr=pr,
                known_pr_shas=known_pr_shas,
                commit_link_cache=commit_link_cache,
            ):
                continue
            seen_ids.add(run_id)
            inspected += 1
            try:
                run_sha = canonical_commit_oid(str(run.get("head_sha") or ""))
            except RuntimeError:
                continue
            if state != "open" or run_sha != authoritative_sha:
                selected.append(run)

    counts = {
        "accepted": 0,
        "forced": 0,
        "moved": 0,
        "deferred": 0,
        "failed": 0,
    }
    for run in selected:
        result = cancel_run(api, context.repo, int(run["id"]))
        counts[result.outcome] += 1
        if result.outcome == "failed":
            print(f"cancel failed: id={run['id']} status={result.status}")

    return {
        "pr": context.pr_number,
        "event_action": context.event_action,
        "live_state": state,
        "authoritative_sha": authoritative_sha,
        "inspected": inspected,
        "selected": len(selected),
        **counts,
    }


def _write_summary(summary: dict[str, int | str]) -> None:
    text = (
        "## Obsolete PR Actions drain\n"
        f"- PR: `#{summary['pr']}`\n"
        f"- Event: `{summary['event_action']}`\n"
        f"- Live PR state: `{summary['live_state']}`\n"
        f"- Authoritative head: `{summary['authoritative_sha']}`\n"
        f"- Matching live runs inspected: {summary['inspected']}\n"
        f"- Obsolete runs selected: {summary['selected']}\n"
        f"- Cancel requests accepted: {summary['accepted']}\n"
        f"- Force-cancel requests accepted: {summary['forced']}\n"
        f"- Already completed/moved: {summary['moved']}\n"
        f"- Transient cancellations deferred: {summary['deferred']}\n"
        f"- Terminal cancellation failures: {summary['failed']}\n"
        "- Trust boundary: workflow + script loaded from the PR base SHA; "
        "pull-request code is never checked out or executed.\n"
    )
    print(" ".join(line.strip() for line in text.splitlines() if line.strip()))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    token = os.environ["GH_TOKEN"]
    context = build_context_from_env()
    api = GitHubApi(token)
    try:
        summary = drain(api, context)
    except RuntimeError as exc:
        print(f"drain failed: {exc}")
        return 1

    _write_summary(summary)
    if int(summary["failed"]) or int(summary["deferred"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
