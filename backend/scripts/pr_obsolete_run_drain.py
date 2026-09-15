"""Trusted workflow-run cleanup for obsolete pull-request Actions runs.

The privileged workflow is loaded from the default branch via ``workflow_run``.
It never consumes artifacts or executes code from the triggering pull request.
The source workflow has no token permissions and exists only as a lifecycle
signal for synchronize/closed events.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

LIVE_STATUSES = ("queued", "in_progress", "waiting", "pending", "requested")
PR_RUN_EVENTS = frozenset({"pull_request", "dynamic"})
BASE_RETRYABLE = frozenset({0, 429, 500, 502, 503, 504})
SIGNAL_WORKFLOW_PATH = ".github/workflows/pr-lifecycle-signal.yml"


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


def _get_json(api: GitHubApi, path: str, *, expected: int = 200) -> Any:
    status, payload, _ = api.request(path)
    if status != expected:
        raise RuntimeError(f"GitHub API GET failed for {path}: HTTP {status}")
    return payload


def fetch_pr(api: GitHubApi, repo: str, pr_number: int) -> dict[str, Any]:
    payload = _get_json(api, f"/repos/{repo}/pulls/{pr_number}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"malformed PR #{pr_number} payload")
    return payload


def fetch_trigger_run(api: GitHubApi, repo: str, run_id: int) -> dict[str, Any]:
    payload = _get_json(api, f"/repos/{repo}/actions/runs/{run_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"malformed trigger workflow run #{run_id}")
    return payload


def list_pr_commit_shas(api: GitHubApi, repo: str, pr_number: int) -> set[str]:
    shas: set[str] = set()
    for page in range(1, 4):
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        payload = _get_json(api, f"/repos/{repo}/pulls/{pr_number}/commits?{query}")
        if not isinstance(payload, list):
            raise RuntimeError(f"malformed PR #{pr_number} commits payload")
        for commit in payload:
            if isinstance(commit, dict) and commit.get("sha"):
                shas.add(str(commit["sha"]))
        if len(payload) < 100:
            break
    return shas


def _associated_pr_numbers(api: GitHubApi, repo: str, sha: str) -> set[int]:
    if not sha:
        return set()
    status, payload, _ = api.request(f"/repos/{repo}/commits/{sha}/pulls")
    if status != 200 or not isinstance(payload, list):
        return set()
    return {
        int(item.get("number") or 0)
        for item in payload
        if isinstance(item, dict) and int(item.get("number") or 0) > 0
    }


def _branch_pr_numbers(
    api: GitHubApi,
    repo: str,
    default_branch: str,
    head_branch: str,
) -> set[int]:
    if not head_branch:
        return set()
    owner = repo.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {
            "state": "all",
            "base": default_branch,
            "head": f"{owner}:{head_branch}",
            "per_page": 100,
        }
    )
    status, payload, _ = api.request(f"/repos/{repo}/pulls?{query}")
    if status != 200 or not isinstance(payload, list):
        return set()
    return {
        int(item.get("number") or 0)
        for item in payload
        if isinstance(item, dict) and int(item.get("number") or 0) > 0
    }


def resolve_context_from_trigger(api: GitHubApi) -> DrainContext | None:
    repo = os.environ["REPO"]
    default_branch = os.environ["DEFAULT_BRANCH"]
    current_run_id = int(os.environ["CURRENT_RUN_ID"])
    trigger_run_id = int(os.environ["TRIGGER_RUN_ID"])
    trigger = fetch_trigger_run(api, repo, trigger_run_id)

    if str(trigger.get("event") or "") != "pull_request":
        raise RuntimeError("refusing non-pull_request workflow_run trigger")
    if str(trigger.get("path") or "") != SIGNAL_WORKFLOW_PATH:
        raise RuntimeError("workflow_run did not originate from the lifecycle signal")
    trigger_repo = _repo_full_name(trigger.get("repository"))
    if trigger_repo and trigger_repo != repo:
        raise RuntimeError("workflow_run repository does not match target repository")

    head_branch = str(trigger.get("head_branch") or "")
    head_sha = str(trigger.get("head_sha") or "")
    trigger_head_repo = _repo_full_name(trigger.get("head_repository"))
    if trigger_head_repo and trigger_head_repo != repo:
        # Fork PRs must not cause privileged Actions mutation. Skipping is cleaner
        # than turning every fork lifecycle event into a failed trusted workflow.
        return None

    numbers = {
        int(item.get("number") or 0)
        for item in trigger.get("pull_requests") or []
        if isinstance(item, dict) and int(item.get("number") or 0) > 0
    }
    if not numbers:
        numbers.update(_associated_pr_numbers(api, repo, head_sha))
    if not numbers:
        numbers.update(_branch_pr_numbers(api, repo, default_branch, head_branch))

    viable: list[dict[str, Any]] = []
    for number in sorted(numbers):
        pr = fetch_pr(api, repo, number)
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        if _repo_full_name(head.get("repo")) != repo:
            continue
        if str(base.get("ref") or "") != default_branch:
            continue
        if head_branch and str(head.get("ref") or "") != head_branch:
            continue
        viable.append(pr)

    if not viable:
        return None
    if len(viable) > 1:
        exact = [
            item
            for item in viable
            if head_sha and str((item.get("head") or {}).get("sha") or "") == head_sha
        ]
        if len(exact) == 1:
            viable = exact
        else:
            raise RuntimeError("ambiguous workflow_run to pull-request association")

    selected = viable[0]
    head = selected.get("head") or {}
    state = str(selected.get("state") or "")
    live_head_sha = str(head.get("sha") or "")
    return DrainContext(
        repo=repo,
        current_run_id=current_run_id,
        pr_number=int(selected["number"]),
        event_action="synchronize" if state == "open" else "closed",
        event_head_repo=_repo_full_name(head.get("repo")),
        event_head_ref=str(head.get("ref") or ""),
        event_head_sha=live_head_sha,
        event_before_sha=head_sha if head_sha != live_head_sha else "",
        default_branch=default_branch,
    )


def list_runs(api: GitHubApi, repo: str, status_name: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for page in range(1, 11):
        query = urllib.parse.urlencode(
            {"status": status_name, "per_page": 100, "page": page}
        )
        status, payload, _ = api.request(f"/repos/{repo}/actions/runs?{query}")
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"failed to list {status_name} runs: HTTP {status}")
        batch = payload.get("workflow_runs") or []
        if not isinstance(batch, list):
            raise RuntimeError(f"malformed {status_name} workflow run payload")
        runs.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
    return runs


def explicit_pr_link(run: dict[str, Any], pr_number: int) -> bool:
    return any(
        isinstance(pull, dict) and int(pull.get("number") or 0) == pr_number
        for pull in run.get("pull_requests") or []
    )


def commit_links_pr(
    api: GitHubApi,
    repo: str,
    sha: str,
    pr_number: int,
    cache: dict[str, bool],
) -> bool:
    if not sha:
        return False
    if sha in cache:
        return cache[sha]
    linked = pr_number in _associated_pr_numbers(api, repo, sha)
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

    sha = str(run.get("head_sha") or "")
    trusted_shas = {
        value
        for value in (
            context.event_head_sha,
            context.event_before_sha,
            str(head.get("sha") or ""),
        )
        if value
    }
    if sha in trusted_shas or sha in known_pr_shas:
        return True
    return commit_links_pr(api, context.repo, sha, context.pr_number, commit_link_cache)


def _run_completed(api: GitHubApi, repo: str, run_id: int) -> bool:
    status, payload, _ = api.request(f"/repos/{repo}/actions/runs/{run_id}")
    return status == 200 and isinstance(payload, dict) and payload.get("status") == "completed"


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
    status, payload = _post_with_retry(api, f"/repos/{repo}/actions/runs/{run_id}/cancel")
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


def drain(api: GitHubApi, context: DrainContext) -> dict[str, int | str]:
    if context.event_head_repo != context.repo:
        raise RuntimeError("refusing privileged cleanup for a cross-repository PR")
    if not context.event_head_ref:
        raise RuntimeError("missing pull-request head ref")
    if context.default_branch == context.event_head_ref:
        raise RuntimeError("refusing PR cleanup whose head is the default branch")

    pr = fetch_pr(api, context.repo, context.pr_number)
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    if _repo_full_name(head.get("repo")) != context.repo:
        raise RuntimeError("pull request is no longer same-repository")
    if str(base.get("ref") or "") != context.default_branch:
        raise RuntimeError("pull request no longer targets the default branch")

    state = str(pr.get("state") or "")
    authoritative_sha = str(head.get("sha") or "") if state == "open" else ""
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
            run_sha = str(run.get("head_sha") or "")
            if state != "open" or run_sha != authoritative_sha:
                selected.append(run)

    counts = {"accepted": 0, "forced": 0, "moved": 0, "deferred": 0, "failed": 0}
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
        f"- Resolved lifecycle: `{summary['event_action']}`\n"
        f"- Live PR state: `{summary['live_state']}`\n"
        f"- Authoritative head: `{summary['authoritative_sha']}`\n"
        f"- Matching live runs inspected: {summary['inspected']}\n"
        f"- Obsolete runs selected: {summary['selected']}\n"
        f"- Cancel requests accepted: {summary['accepted']}\n"
        f"- Force-cancel requests accepted: {summary['forced']}\n"
        f"- Already completed/moved: {summary['moved']}\n"
        f"- Transient cancellations deferred: {summary['deferred']}\n"
        f"- Terminal cancellation failures: {summary['failed']}\n"
        "- Trust boundary: privileged workflow and script come from the default branch; "
        "the unprivileged source workflow contributes no artifacts or executable code.\n"
    )
    print(" ".join(line.strip() for line in text.splitlines() if line.strip()))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    api = GitHubApi(os.environ["GH_TOKEN"])
    try:
        context = resolve_context_from_trigger(api)
        if context is None:
            print("drain skipped: trigger does not resolve to a same-repository default-branch PR")
            return 0
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
