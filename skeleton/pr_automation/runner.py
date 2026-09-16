"""GitHub runtime adapter for the PR automation policy engine.

The privileged workflow executes trusted default-branch code only. Apply mode
requires a protected base branch, revalidates the complete policy snapshot
immediately before mutation, and still sends GitHub an expected-head SHA so
server-side rules are the final authority for the narrow race window.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .core import CIState, Decision, Evaluation, Mode, PRSnapshot, Policy, evaluate
from .index import EventIndex


API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
GATE_CONTEXT = "PR Automation Gate"
TERMINAL_FAILURES = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}
PENDING_STATES = {"queued", "in_progress", "pending", "requested", "waiting"}
_STATE_SEVERITY = {"passing": 0, "unknown": 1, "pending": 2, "failing": 3}


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    mutations: int
    snapshot: PRSnapshot
    evaluation: Evaluation


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
            "User-Agent": "skeleton-pr-automation/2",
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
                retryable = (
                    exc.code in {429, 500, 502, 503, 504}
                    or remaining == "0"
                    or (exc.code == 403 and bool(retry_after))
                )
                if not retryable or attempt >= self.retries:
                    detail = exc.read().decode("utf-8", errors="replace")[:1000]
                    raise GitHubError(f"GitHub HTTP {exc.code}: {detail}") from exc
                if retry_after and retry_after.isdigit():
                    delay = min(30, int(retry_after))
                elif remaining == "0" and reset and reset.isdigit():
                    delay = min(30, max(1, int(reset) - int(time.time())))
                else:
                    delay = min(8, 2**attempt)
                time.sleep(delay)
            except (URLError, TimeoutError) as exc:
                if attempt >= self.retries:
                    raise GitHubError(f"GitHub request failed: {exc}") from exc
                time.sleep(min(8, 2**attempt))
        raise AssertionError("unreachable")

    def get(self, path: str) -> Any:
        return self.request("GET", f"{API}{path}")

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        result = self.request("POST", GRAPHQL, {"query": query, "variables": variables})
        if not isinstance(result, dict) or result.get("errors"):
            errors = result.get("errors") if isinstance(result, dict) else result
            raise GitHubError(f"GraphQL errors: {errors!r}")
        return result["data"]


def _recency(item: dict[str, Any]) -> tuple[str, int]:
    timestamp = str(
        item.get("completed_at")
        or item.get("updated_at")
        or item.get("submitted_at")
        or item.get("started_at")
        or item.get("created_at")
        or ""
    )
    try:
        numeric_id = int(item.get("id") or 0)
    except (TypeError, ValueError):
        numeric_id = 0
    return timestamp, numeric_id


def _check_state(run: dict[str, Any]) -> str:
    status = str(run.get("status") or "").casefold()
    conclusion = str(run.get("conclusion") or "").casefold()
    if status != "completed":
        return "pending"
    if conclusion == "success":
        return "passing"
    if conclusion in TERMINAL_FAILURES:
        return "failing"
    # neutral/skipped and new conclusion values do not satisfy a required gate.
    return "unknown"


def _legacy_status_state(status: dict[str, Any]) -> str:
    state = str(status.get("state") or "").casefold()
    if state == "success":
        return "passing"
    if state in {"failure", "error"}:
        return "failing"
    if state in PENDING_STATES:
        return "pending"
    return "unknown"


def aggregate_ci(
    check_runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    required: set[str],
) -> CIState:
    """Collapse CI into a conservative state without stale-rerun overrides.

    The newest run is selected per check-name/provider pair, then different
    providers with the same name are combined pessimistically. A third-party
    passing check therefore cannot overwrite a failing GitHub Actions check.
    """

    providers: dict[tuple[str, str], tuple[tuple[str, int], str]] = {}
    for run in check_runs:
        name = str(run.get("name") or "").strip()
        if not name:
            continue
        app = run.get("app") or {}
        provider = str(app.get("id") or app.get("slug") or "unknown")
        key = (name, f"check:{provider}")
        candidate = (_recency(run), _check_state(run))
        prior = providers.get(key)
        if prior is None or candidate[0] >= prior[0]:
            providers[key] = candidate

    for status in statuses:
        name = str(status.get("context") or "").strip()
        if not name or name == GATE_CONTEXT:
            continue
        key = (name, "legacy-status")
        candidate = (_recency(status), _legacy_status_state(status))
        prior = providers.get(key)
        if prior is None or candidate[0] >= prior[0]:
            providers[key] = candidate

    states_by_name: dict[str, list[str]] = {}
    for (name, _provider), (_rank, state) in providers.items():
        states_by_name.setdefault(name, []).append(state)

    observed = {
        name: max(states, key=lambda state: _STATE_SEVERITY[state])
        for name, states in states_by_name.items()
    }
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


def latest_reviews(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_user: dict[str, dict[str, Any]] = {}
    for review in reviews:
        user = ((review.get("user") or {}).get("login") or "").casefold()
        state = str(review.get("state") or "").upper()
        if not user or state == "COMMENTED":
            continue
        prior = by_user.get(user)
        if prior is None or _recency(review) >= _recency(prior):
            by_user[user] = review
    return by_user


def latest_review_states(reviews: list[dict[str, Any]]) -> dict[str, str]:
    return {
        user: str(review.get("state") or "").upper()
        for user, review in latest_reviews(reviews).items()
    }


def count_approvals(reviews: list[dict[str, Any]], head_sha: str | None = None) -> int:
    count = 0
    for review in latest_reviews(reviews).values():
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        if head_sha is not None:
            reviewed_sha = str(review.get("commit_id") or "")
            if not reviewed_sha or reviewed_sha.casefold() != head_sha.casefold():
                continue
        count += 1
    return count


def count_changes_requested(reviews: list[dict[str, Any]]) -> int:
    return sum(
        1
        for review in latest_reviews(reviews).values()
        if str(review.get("state") or "").upper() == "CHANGES_REQUESTED"
    )


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
        # Do not silently ignore review threads beyond the first 100.
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
    total: int | None = None
    for page in range(1, max_pages + 1):
        payload = client.get(f"/repos/{owner}/{name}/commits/{sha}/check-runs?per_page=100&page={page}")
        if not isinstance(payload, dict):
            raise GitHubError("invalid check-runs response")
        batch = payload.get("check_runs", [])
        if not isinstance(batch, list):
            raise GitHubError("invalid check-runs list")
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
    if not isinstance(pr, dict):
        raise GitHubError("invalid pull request response")
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

    ci_state = (
        aggregate_ci(check_runs, statuses, required_checks)
        if checks_complete and statuses_complete
        else CIState.UNKNOWN
    )
    try:
        thread_count = unresolved_threads(client, repository, number)
    except (GitHubError, KeyError, TypeError):
        thread_count = None

    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if reviews_complete:
        approvals = count_approvals(reviews, head_sha=head_sha)
        changes_requested = count_changes_requested(reviews)
    else:
        approvals = None
        changes_requested = None

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
        # A missing head repo commonly means a deleted fork; treat it as external/unknown.
        from_fork=not head_repo or str(head_repo).casefold() != repository.casefold(),
        mergeable=pr.get("mergeable"),
        mergeable_state=str(pr.get("mergeable_state") or "unknown"),
        ci_state=ci_state,
        approvals=approvals,
        changes_requested=changes_requested,
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


def _status_url(repository: str, sha: str) -> str:
    owner, name = repository.split("/", 1)
    return f"{API}/repos/{owner}/{name}/statuses/{sha}"


def publish_gate_status(
    client: GitHubClient,
    snapshot: PRSnapshot,
    evaluation: Evaluation,
    *,
    force_state: str | None = None,
    description: str | None = None,
) -> None:
    if not snapshot.head_sha:
        return
    if force_state is not None:
        state = force_state
    elif evaluation.decision in {Decision.READY, Decision.MERGE}:
        state = "success"
    elif evaluation.decision is Decision.HOLD and snapshot.ci_state is CIState.FAILING:
        state = "failure"
    else:
        state = "pending"

    message = description or (evaluation.reasons[0] if evaluation.reasons else evaluation.decision.value)
    body: dict[str, Any] = {
        "state": state,
        "context": GATE_CONTEXT,
        "description": message[:140],
    }
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_id = os.getenv("GITHUB_RUN_ID")
    if run_id:
        body["target_url"] = f"{server}/{snapshot.repository}/actions/runs/{run_id}"
    client.request("POST", _status_url(snapshot.repository, snapshot.head_sha), body)


def base_is_protected(client: GitHubClient, repository: str, base_ref: str) -> bool:
    owner, name = repository.split("/", 1)
    branch = client.get(f"/repos/{owner}/{name}/branches/{quote(base_ref, safe='')}")
    return isinstance(branch, dict) and branch.get("protected") is True


def _operational_hold(snapshot: PRSnapshot, evaluation: Evaluation, reason: str) -> Evaluation:
    return Evaluation(
        decision=Decision.HOLD,
        reasons=(reason,),
        snapshot_fingerprint=snapshot.fingerprint(),
        policy_fingerprint=evaluation.policy_fingerprint,
    )


def execute_actions(
    client: GitHubClient,
    index: EventIndex,
    snapshot: PRSnapshot,
    evaluation: Evaluation,
    *,
    policy: Policy,
    required_checks: set[str],
    mode: Mode,
    max_mutations: int,
    delivery_id: str | None,
    merge_method: str,
    refresh_snapshot: Callable[[], PRSnapshot] | None = None,
) -> ActionOutcome:
    if mode is Mode.OBSERVE or not evaluation.actions:
        return ActionOutcome(0, snapshot, evaluation)

    if max_mutations <= 0:
        index.append(
            snapshot=snapshot,
            evaluation=evaluation,
            event_type="mutation_budget_exhausted",
            delivery_id=f"{delivery_id}:budget" if delivery_id else None,
        )
        return ActionOutcome(0, snapshot, evaluation)
    if len(evaluation.actions) > max_mutations:
        raise RuntimeError(f"mutation cap exceeded: {len(evaluation.actions)} > {max_mutations}")

    if refresh_snapshot is None:
        refresh_snapshot = lambda: fetch_snapshot(
            client,
            snapshot.repository,
            snapshot.number,
            required_checks,
        )[0]

    live_snapshot = refresh_snapshot()
    live_evaluation = evaluate(live_snapshot, policy)
    same_plan = (
        live_snapshot.fingerprint() == snapshot.fingerprint()
        and live_evaluation.decision is Decision.MERGE
        and tuple(action.idempotency_key for action in live_evaluation.actions)
        == tuple(action.idempotency_key for action in evaluation.actions)
    )
    if not same_plan:
        held = (
            live_evaluation
            if live_evaluation.decision is not Decision.MERGE
            else _operational_hold(
                live_snapshot,
                live_evaluation,
                "policy-relevant PR state changed after evaluation; plan discarded",
            )
        )
        index.append(
            snapshot=live_snapshot,
            evaluation=held,
            event_type="stale_plan",
            delivery_id=f"{delivery_id}:stale" if delivery_id else None,
            extra={"original_snapshot_fingerprint": snapshot.fingerprint()},
        )
        publish_gate_status(client, live_snapshot, held)
        return ActionOutcome(0, live_snapshot, held)

    if not base_is_protected(client, live_snapshot.repository, live_snapshot.base_ref):
        held = _operational_hold(
            live_snapshot,
            live_evaluation,
            "apply mode requires a protected base branch/ruleset",
        )
        index.append(
            snapshot=live_snapshot,
            evaluation=held,
            event_type="unprotected_base",
            delivery_id=f"{delivery_id}:unprotected" if delivery_id else None,
        )
        publish_gate_status(client, live_snapshot, held)
        return ActionOutcome(0, live_snapshot, held)

    owner, name = live_snapshot.repository.split("/", 1)
    mutations = 0
    for action in live_evaluation.actions:
        claimed = index.claim_action(
            idempotency_key=action.idempotency_key,
            repository=live_snapshot.repository,
            pr_number=live_snapshot.number,
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
                f"{API}/repos/{owner}/{name}/pulls/{live_snapshot.number}/merge",
                {"sha": action.expected_head_sha, "merge_method": merge_method},
            )
            if not isinstance(result, dict) or not result.get("merged"):
                message = result.get("message", "unknown reason") if isinstance(result, dict) else result
                raise GitHubError(f"merge rejected: {message}")
            index.finish_action(action.idempotency_key, success=True)
            index.append(
                snapshot=live_snapshot,
                evaluation=live_evaluation,
                event_type="action:merge:succeeded",
                delivery_id=f"{delivery_id}:merge" if delivery_id else None,
                extra={"merge_sha": result.get("sha"), "merge_method": merge_method},
            )
            mutations += 1
        except Exception as exc:
            index.finish_action(action.idempotency_key, success=False, error=str(exc))
            index.append(
                snapshot=live_snapshot,
                evaluation=live_evaluation,
                event_type="action:merge:failed",
                delivery_id=f"{delivery_id}:merge-failed" if delivery_id else None,
                extra={"error": f"{type(exc).__name__}: {exc}"},
            )
            raise
    return ActionOutcome(mutations, live_snapshot, live_evaluation)


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


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
        dict.fromkeys(
            part.strip()
            for part in os.getenv("PR_AUTOMATION_ALLOWED_BASES", "main").split(",")
            if part.strip()
        )
    )
    if not allowed:
        raise ValueError("PR_AUTOMATION_ALLOWED_BASES must contain at least one branch")
    return Policy(
        allowed_bases=allowed,
        required_approvals=_int_env("PR_AUTOMATION_REQUIRED_APPROVALS", 0, minimum=0, maximum=50),
        require_no_changes_requested=_bool_env("PR_AUTOMATION_REQUIRE_NO_CHANGES_REQUESTED", True),
        require_resolved_threads=_bool_env("PR_AUTOMATION_REQUIRE_RESOLVED_THREADS", True),
        require_checks=_bool_env("PR_AUTOMATION_REQUIRE_CHECKS", True),
        allow_fork_merge=_bool_env("PR_AUTOMATION_ALLOW_FORK_MERGE", False),
        max_changed_files=_int_env("PR_AUTOMATION_MAX_CHANGED_FILES", 250, minimum=1, maximum=3000),
        max_total_line_delta=_int_env(
            "PR_AUTOMATION_MAX_LINE_DELTA",
            20_000,
            minimum=1,
            maximum=10_000_000,
        ),
        merge_when_ready=_bool_env("PR_AUTOMATION_MERGE_WHEN_READY", False),
    )


def required_checks_from_env() -> set[str]:
    checks = {
        item.strip()
        for item in os.getenv("PR_AUTOMATION_REQUIRED_CHECKS", "").split(",")
        if item.strip()
    }
    if GATE_CONTEXT in checks:
        raise ValueError(f"{GATE_CONTEXT!r} cannot require itself")
    return checks


def list_open_prs(client: GitHubClient, repository: str, limit: int) -> list[int]:
    owner, name = repository.split("/", 1)
    limit = min(max(1, limit), 1000)
    payload, _complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/pulls?state=open&sort=updated&direction=desc",
        max_pages=max(1, (limit + 99) // 100),
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
) -> ActionOutcome:
    if not index.verify_chain(repository, number):
        raise RuntimeError(f"event-index hash chain failed for {repository}#{number}")

    snapshot, _ = fetch_snapshot(client, repository, number, required_checks)
    evaluation = evaluate(snapshot, policy)
    index.append(
        snapshot=snapshot,
        evaluation=evaluation,
        event_type="evaluation",
        delivery_id=delivery_id,
        extra={"mode": mode.value, "mutation_budget": max_mutations},
    )
    if evaluation.decision is not Decision.IGNORE:
        # Publish readiness before merge so a ruleset may require this trusted context.
        publish_gate_status(client, snapshot, evaluation)

    return execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks=required_checks,
        mode=mode,
        max_mutations=max_mutations,
        delivery_id=delivery_id,
        merge_method=merge_method,
    )


def _publish_run_error(client: GitHubClient, repository: str, number: int, message: str) -> None:
    try:
        owner, name = repository.split("/", 1)
        pr = client.get(f"/repos/{owner}/{name}/pulls/{number}")
        head_sha = str((pr.get("head") or {}).get("sha") or "") if isinstance(pr, dict) else ""
        if not head_sha:
            return
        snapshot = PRSnapshot(
            repository=repository,
            number=number,
            head_sha=head_sha,
            base_sha="unknown00",
            base_ref="unknown",
            head_ref="unknown",
        )
        placeholder = Evaluation(
            decision=Decision.HOLD,
            reasons=(message,),
            snapshot_fingerprint=snapshot.fingerprint(),
            policy_fingerprint="runtime-error",
        )
        publish_gate_status(client, snapshot, placeholder, force_state="error", description=message)
    except Exception:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and safely automate pull requests.")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--index", default=os.getenv("PR_AUTOMATION_INDEX", ".pr-automation/index.sqlite3"))
    parser.add_argument("--export", default=os.getenv("PR_AUTOMATION_EXPORT", ".pr-automation/index.jsonl"))
    args = parser.parse_args(argv)

    if not args.repo or args.repo.count("/") != 1:
        parser.error("--repo or GITHUB_REPOSITORY must be owner/name")
    if args.pr is not None and args.pr <= 0:
        parser.error("--pr must be positive")
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")

    token = os.getenv("GITHUB_TOKEN", "")
    mode = Mode(os.getenv("PR_AUTOMATION_MODE", "observe").casefold())
    max_mutations = _int_env("PR_AUTOMATION_MAX_MUTATIONS", 1, minimum=0, maximum=10)
    merge_method = os.getenv("PR_AUTOMATION_MERGE_METHOD", "squash").casefold()
    if merge_method not in {"merge", "squash", "rebase"}:
        raise ValueError("PR_AUTOMATION_MERGE_METHOD must be merge, squash, or rebase")

    client = GitHubClient(token)
    index = EventIndex(args.index)
    policy = policy_from_env()
    checks = required_checks_from_env()

    if mode is Mode.APPLY and policy.merge_when_ready:
        if max_mutations < 1:
            raise ValueError("apply+merge requires PR_AUTOMATION_MAX_MUTATIONS >= 1")
        if not policy.require_checks or not checks:
            raise ValueError("apply+merge requires checks and explicit PR_AUTOMATION_REQUIRED_CHECKS")

    base_delivery = os.getenv("GITHUB_RUN_ID") or os.getenv("GITHUB_DELIVERY_ID")
    numbers = [args.pr] if args.pr else list_open_prs(client, args.repo, args.limit)
    failures = 0
    remaining_mutations = max_mutations

    for number in numbers:
        try:
            delivery = f"{base_delivery}:{number}" if base_delivery else None
            outcome = run_one(
                client,
                index,
                args.repo,
                number,
                policy=policy,
                required_checks=checks,
                mode=mode,
                delivery_id=delivery,
                max_mutations=remaining_mutations,
                merge_method=merge_method,
            )
            remaining_mutations = max(0, remaining_mutations - outcome.mutations)
        except Exception as exc:
            failures += 1
            message = f"{type(exc).__name__}: {exc}"
            print(f"PR #{number}: {message}", file=sys.stderr)
            _publish_run_error(client, args.repo, number, message)

    index.export_jsonl(args.export)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
