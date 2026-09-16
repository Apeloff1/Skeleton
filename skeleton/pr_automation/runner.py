"""GitHub runtime adapter for the PR automation policy engine.

The privileged workflow never checks out PR head code. It only reads GitHub
metadata, evaluates trusted default-branch policy code, and optionally performs
a single SHA-preconditioned merge.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import CIState, Decision, Evaluation, Mode, PRSnapshot, Policy, evaluate
from .index import EventIndex


API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
TERMINAL_FAILURES = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
PENDING_STATES = {"queued", "in_progress", "pending", "requested", "waiting"}


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str, *, retries: int = 3):
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.retries = max(0, retries)

    def request(self, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "skeleton-pr-automation/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(self.retries + 1):
            req = Request(url, data=encoded, headers=headers, method=method)
            try:
                with urlopen(req, timeout=30) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload) if payload else None
            except HTTPError as exc:
                retry_after = exc.headers.get("Retry-After")
                remaining = exc.headers.get("X-RateLimit-Remaining")
                reset = exc.headers.get("X-RateLimit-Reset")
                retryable = exc.code in {429, 500, 502, 503, 504} or remaining == "0"
                if not retryable or attempt >= self.retries:
                    detail = exc.read().decode("utf-8", errors="replace")[:1000]
                    raise GitHubError(f"GitHub HTTP {exc.code}: {detail}") from exc
                if retry_after and retry_after.isdigit():
                    delay = min(30, int(retry_after))
                elif remaining == "0" and reset and reset.isdigit():
                    delay = min(30, max(1, int(reset) - int(time.time())))
                else:
                    delay = min(8, 2 ** attempt)
                time.sleep(delay)
            except (URLError, TimeoutError) as exc:
                if attempt >= self.retries:
                    raise GitHubError(f"GitHub request failed: {exc}") from exc
                time.sleep(min(8, 2 ** attempt))
        raise AssertionError("unreachable")

    def get(self, path: str) -> Any:
        return self.request("GET", f"{API}{path}")

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        result = self.request("POST", GRAPHQL, {"query": query, "variables": variables})
        if result.get("errors"):
            raise GitHubError(f"GraphQL errors: {result['errors']!r}")
        return result["data"]


def aggregate_ci(
    check_runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    required: set[str],
) -> CIState:
    """Collapse check-runs and legacy statuses into a conservative CI state."""
    observed: dict[str, str] = {}

    for run in check_runs:
        name = str(run.get("name") or "").strip()
        if not name:
            continue
        status = str(run.get("status") or "").casefold()
        conclusion = str(run.get("conclusion") or "").casefold()
        if status != "completed":
            observed[name] = "pending"
        elif conclusion in {"success", "neutral", "skipped"}:
            observed[name] = "passing"
        elif conclusion in TERMINAL_FAILURES or conclusion:
            observed[name] = "failing"
        else:
            observed[name] = "unknown"

    for status in statuses:
        name = str(status.get("context") or "").strip()
        if not name:
            continue
        state = str(status.get("state") or "").casefold()
        if state == "success":
            observed.setdefault(name, "passing")
        elif state in {"failure", "error"}:
            observed[name] = "failing"
        elif state in PENDING_STATES:
            observed[name] = "pending"
        else:
            observed.setdefault(name, "unknown")

    names = required if required else set(observed)
    if not names:
        return CIState.MISSING
    if required and not required.issubset(observed):
        return CIState.MISSING

    states = {observed.get(name, "missing") for name in names}
    if "failing" in states:
        return CIState.FAILING
    if "missing" in states:
        return CIState.MISSING
    if "pending" in states:
        return CIState.PENDING
    if "unknown" in states:
        return CIState.UNKNOWN
    return CIState.PASSING


def latest_review_states(reviews: list[dict[str, Any]]) -> dict[str, str]:
    by_user: dict[str, tuple[str, str]] = {}
    for review in reviews:
        user = ((review.get("user") or {}).get("login") or "").casefold()
        state = str(review.get("state") or "").upper()
        submitted = str(review.get("submitted_at") or "")
        if not user or state == "COMMENTED":
            continue
        prior = by_user.get(user)
        if prior is None or submitted >= prior[0]:
            by_user[user] = (submitted, state)
    return {user: value[1] for user, value in by_user.items()}


def count_approvals(reviews: list[dict[str, Any]]) -> int:
    return sum(1 for state in latest_review_states(reviews).values() if state == "APPROVED")


THREADS_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes { isResolved }
        pageInfo { hasNextPage }
      }
    }
  }
}
"""


def unresolved_threads(client: GitHubClient, repository: str, number: int) -> int | None:
    owner, name = repository.split("/", 1)
    data = client.graphql(THREADS_QUERY, {"owner": owner, "name": name, "number": number})
    threads = data["repository"]["pullRequest"]["reviewThreads"]
    if threads["pageInfo"]["hasNextPage"]:
        # Fail closed rather than silently ignoring threads beyond the first 100.
        return None
    return sum(1 for node in threads["nodes"] if not node["isResolved"])


def _paged_list(client: GitHubClient, path: str, *, max_pages: int = 10) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        batch = client.get(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise GitHubError(f"expected list response for {path}")
        items.extend(batch)
        if len(batch) < 100:
            return items, True
    return items, False


def _paged_check_runs(
    client: GitHubClient,
    owner: str,
    name: str,
    sha: str,
    *,
    max_pages: int = 10,
) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    total = None
    for page in range(1, max_pages + 1):
        payload = client.get(f"/repos/{owner}/{name}/commits/{sha}/check-runs?per_page=100&page={page}")
        batch = payload.get("check_runs", [])
        total = int(payload.get("total_count") or len(batch))
        items.extend(batch)
        if len(items) >= total:
            return items, True
        if len(batch) < 100:
            return items, len(items) >= total
    return items, total is not None and len(items) >= total


def fetch_snapshot(
    client: GitHubClient,
    repository: str,
    number: int,
    required_checks: set[str],
) -> tuple[PRSnapshot, dict[str, Any]]:
    owner, name = repository.split("/", 1)
    pr = client.get(f"/repos/{owner}/{name}/pulls/{number}")
    head_sha = str((pr.get("head") or {}).get("sha") or "")

    check_runs, checks_complete = _paged_check_runs(client, owner, name, head_sha)
    statuses, statuses_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/commits/{head_sha}/statuses",
    )
    reviews, reviews_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/pulls/{number}/reviews",
    )

    if checks_complete and statuses_complete:
        ci_state = aggregate_ci(check_runs, statuses, required_checks)
    else:
        ci_state = CIState.UNKNOWN

    try:
        thread_count = unresolved_threads(client, repository, number)
    except (GitHubError, KeyError, TypeError):
        thread_count = None

    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    snapshot = PRSnapshot(
        repository=repository,
        number=number,
        head_sha=head_sha,
        base_sha=str((pr.get("base") or {}).get("sha") or ""),
        base_ref=str((pr.get("base") or {}).get("ref") or ""),
        head_ref=str((pr.get("head") or {}).get("ref") or ""),
        state=str(pr.get("state") or "unknown"),
        merged=bool(pr.get("merged")),
        draft=bool(pr.get("draft")),
        from_fork=bool(head_repo and head_repo.casefold() != repository.casefold()),
        mergeable=pr.get("mergeable"),
        mergeable_state=str(pr.get("mergeable_state") or "unknown"),
        ci_state=ci_state,
        approvals=count_approvals(reviews) if reviews_complete else None,
        unresolved_threads=thread_count,
        changed_files=int(pr.get("changed_files") or 0),
        additions=int(pr.get("additions") or 0),
        deletions=int(pr.get("deletions") or 0),
        labels=tuple(
            sorted(str(item.get("name") or "") for item in pr.get("labels", []) if item.get("name"))
        ),
        updated_at=pr.get("updated_at"),
    )
    return snapshot, pr


def execute_actions(
    client: GitHubClient,
    index: EventIndex,
    snapshot: PRSnapshot,
    evaluation: Evaluation,
    *,
    mode: Mode,
    max_mutations: int,
    delivery_id: str | None,
    merge_method: str,
) -> int:
    if mode is Mode.OBSERVE or not evaluation.actions:
        return 0

    if len(evaluation.actions) > max_mutations:
        raise RuntimeError(f"mutation cap exceeded: {len(evaluation.actions)} > {max_mutations}")

    owner, name = snapshot.repository.split("/", 1)
    live = client.get(f"/repos/{owner}/{name}/pulls/{snapshot.number}")
    live_sha = str((live.get("head") or {}).get("sha") or "")
    if bool(live.get("merged")):
        return 0
    if live_sha != snapshot.head_sha:
        stale = Evaluation(
            decision=Decision.HOLD,
            reasons=("head SHA changed after evaluation; stale plan discarded",),
            snapshot_fingerprint=snapshot.fingerprint(),
            policy_fingerprint=evaluation.policy_fingerprint,
        )
        index.append(
            snapshot=snapshot,
            evaluation=stale,
            event_type="stale_plan",
            delivery_id=f"{delivery_id}:stale" if delivery_id else None,
            extra={"observed_head_sha": live_sha},
        )
        return 0

    mutations = 0
    for action in evaluation.actions:
        if action.expected_head_sha != live_sha:
            break
        claimed = index.claim_action(
            idempotency_key=action.idempotency_key,
            repository=snapshot.repository,
            pr_number=snapshot.number,
            expected_head_sha=action.expected_head_sha,
            action_kind=action.kind,
        )
        if not claimed:
            continue

        try:
            if action.kind != "merge":
                raise RuntimeError(f"unsupported planned action: {action.kind}")
            result = client.request(
                "PUT",
                f"{API}/repos/{owner}/{name}/pulls/{snapshot.number}/merge",
                {"sha": action.expected_head_sha, "merge_method": merge_method},
            )
            if not result.get("merged"):
                raise GitHubError(f"merge rejected: {result.get('message', 'unknown reason')}")
            index.finish_action(action.idempotency_key, success=True)
            index.append(
                snapshot=snapshot,
                evaluation=evaluation,
                event_type="action:merge:succeeded",
                delivery_id=f"{delivery_id}:merge" if delivery_id else None,
                extra={"merge_sha": result.get("sha"), "merge_method": merge_method},
            )
            mutations += 1
        except Exception as exc:
            index.finish_action(action.idempotency_key, success=False, error=str(exc))
            index.append(
                snapshot=snapshot,
                evaluation=evaluation,
                event_type="action:merge:failed",
                delivery_id=f"{delivery_id}:merge-failed" if delivery_id else None,
                extra={"error": f"{type(exc).__name__}: {exc}"},
            )
            raise
    return mutations


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    if raw.casefold() in {"1", "true", "yes", "on"}:
        return True
    if raw.casefold() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def policy_from_env() -> Policy:
    allowed = tuple(
        filter(
            None,
            (part.strip() for part in os.getenv("PR_AUTOMATION_ALLOWED_BASES", "main").split(",")),
        )
    )
    return Policy(
        allowed_bases=allowed or ("main",),
        required_approvals=max(0, _int_env("PR_AUTOMATION_REQUIRED_APPROVALS", 0)),
        require_resolved_threads=_bool_env("PR_AUTOMATION_REQUIRE_RESOLVED_THREADS", True),
        require_checks=_bool_env("PR_AUTOMATION_REQUIRE_CHECKS", True),
        allow_fork_merge=_bool_env("PR_AUTOMATION_ALLOW_FORK_MERGE", False),
        max_changed_files=max(1, _int_env("PR_AUTOMATION_MAX_CHANGED_FILES", 250)),
        max_total_line_delta=max(1, _int_env("PR_AUTOMATION_MAX_LINE_DELTA", 20_000)),
        merge_when_ready=_bool_env("PR_AUTOMATION_MERGE_WHEN_READY", False),
    )


def required_checks_from_env() -> set[str]:
    return {
        item.strip()
        for item in os.getenv("PR_AUTOMATION_REQUIRED_CHECKS", "").split(",")
        if item.strip()
    }


def list_open_prs(client: GitHubClient, repository: str, limit: int) -> list[int]:
    owner, name = repository.split("/", 1)
    payload = client.get(
        f"/repos/{owner}/{name}/pulls?state=open&sort=updated&direction=desc&per_page={min(limit, 100)}"
    )
    return [int(pr["number"]) for pr in payload[:limit]]


def run_one(
    client: GitHubClient,
    index: EventIndex,
    repository: str,
    number: int,
    *,
    policy: Policy,
    required_checks: set[str],
    mode: Mode,
    delivery_id: str | None,
    max_mutations: int,
    merge_method: str,
) -> int:
    if not index.verify_chain(repository, number):
        raise RuntimeError(f"event-index hash chain failed for {repository}#{number}")

    snapshot, _ = fetch_snapshot(client, repository, number, required_checks)
    evaluation = evaluate(snapshot, policy)
    index.append(
        snapshot=snapshot,
        evaluation=evaluation,
        event_type="evaluation",
        delivery_id=delivery_id,
        extra={"mode": mode.value},
    )
    return execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        mode=mode,
        max_mutations=max_mutations,
        delivery_id=delivery_id,
        merge_method=merge_method,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and safely automate pull requests.")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--index", default=os.getenv("PR_AUTOMATION_INDEX", ".pr-automation/index.sqlite3"))
    parser.add_argument("--export", default=os.getenv("PR_AUTOMATION_EXPORT", ".pr-automation/index.jsonl"))
    args = parser.parse_args(argv)

    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")

    token = os.getenv("GITHUB_TOKEN", "")
    mode = Mode(os.getenv("PR_AUTOMATION_MODE", "observe").casefold())
    max_mutations = max(0, _int_env("PR_AUTOMATION_MAX_MUTATIONS", 1))
    merge_method = os.getenv("PR_AUTOMATION_MERGE_METHOD", "squash").casefold()
    if merge_method not in {"merge", "squash", "rebase"}:
        raise ValueError("PR_AUTOMATION_MERGE_METHOD must be merge, squash, or rebase")

    client = GitHubClient(token)
    index = EventIndex(args.index)
    policy = policy_from_env()
    checks = required_checks_from_env()

    if mode is Mode.APPLY:
        if max_mutations < 1:
            raise ValueError("apply mode requires PR_AUTOMATION_MAX_MUTATIONS >= 1")
        if policy.merge_when_ready and policy.require_checks and not checks:
            raise ValueError("apply+merge requires explicit PR_AUTOMATION_REQUIRED_CHECKS")

    base_delivery = os.getenv("GITHUB_RUN_ID") or os.getenv("GITHUB_DELIVERY_ID")
    numbers = [args.pr] if args.pr else list_open_prs(client, args.repo, max(1, args.limit))
    failures = 0

    for number in numbers:
        try:
            delivery = f"{base_delivery}:{number}" if base_delivery else None
            run_one(
                client,
                index,
                args.repo,
                number,
                policy=policy,
                required_checks=checks,
                mode=mode,
                delivery_id=delivery,
                max_mutations=max_mutations,
                merge_method=merge_method,
            )
        except Exception as exc:
            failures += 1
            print(f"PR #{number}: {type(exc).__name__}: {exc}", file=sys.stderr)

    index.export_jsonl(args.export)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
