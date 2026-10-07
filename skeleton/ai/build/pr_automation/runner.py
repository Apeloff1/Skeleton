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
import re
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .core import CIState, Decision, Evaluation, Mode, PRSnapshot, Policy, evaluate
from .event_firewall import admit_workflow_run, event_from_env
from .index import EventIndex
from .safety import load_operator_safety


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
COMMIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_STATE_SEVERITY = {"passing": 0, "unknown": 1, "pending": 2, "failing": 3}
SENSITIVE_PREFIXES = (
    ".github/workflows/",
    ".github/ci/",
    "skeleton/pr_automation/",
)
SENSITIVE_FILES = {
    "scripts/check_merge_readiness_contract.py",
    "scripts/quality-gates.sh",
    "tests/run_unit.py",
}


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
    """Collapse CI into a conservative state without stale-rerun overrides."""

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
            try:
                expected = canonical_commit_oid(head_sha)
                reviewed_sha = canonical_commit_oid(str(review.get("commit_id") or ""))
            except GitHubError:
                continue
            if reviewed_sha != expected:
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
        payload = client.get(
            f"/repos/{owner}/{name}/commits/{quote(sha, safe='')}/check-runs?per_page=100&page={page}"
        )
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


def _scan_sensitive_paths(files: list[dict[str, Any]]) -> tuple[str, ...]:
    paths = []
    for item in files:
        filename = str(item.get("filename") or "")
        if filename in SENSITIVE_FILES or filename.startswith(SENSITIVE_PREFIXES):
            paths.append(filename)
    return tuple(sorted(set(paths)))


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
    head_sha = canonical_commit_oid(str((pr.get("head") or {}).get("sha") or ""))
    base_sha = canonical_commit_oid(str((pr.get("base") or {}).get("sha") or ""))
    quoted_sha = quote(head_sha, safe="")

    check_runs, checks_complete = _paged_check_runs(client, owner, name, head_sha)
    statuses, statuses_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/commits/{quoted_sha}/statuses",
    )
    reviews, reviews_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/pulls/{number}/reviews",
    )
    files, files_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/pulls/{number}/files",
        max_pages=30,
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
        base_sha=base_sha,
        base_ref=str((pr.get("base") or {}).get("ref") or ""),
        head_ref=str((pr.get("head") or {}).get("ref") or ""),
        state=str(pr.get("state") or "unknown"),
        merged=bool(pr.get("merged")),
        draft=bool(pr.get("draft")),
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
        sensitive_paths=_scan_sensitive_paths(files) if files_complete else None,
        labels=tuple(
            sorted(str(item.get("name") or "") for item in pr.get("labels", []) if item.get("name"))
        ),
        updated_at=pr.get("updated_at"),
    )
    return snapshot, pr


def _status_url(repository: str, sha: str) -> str:
    owner, name = repository.split("/", 1)
    quoted_sha = quote(canonical_commit_oid(sha), safe="")
    return f"{API}/repos/{owner}/{name}/statuses/{quoted_sha}"


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


def queued_actions_count(client: GitHubClient, repository: str) -> int:
    owner, name = repository.split("/", 1)
    payload = client.get(
        f"/repos/{owner}/{name}/actions/runs?status=queued&per_page=1"
    )
    if not isinstance(payload, dict):
        raise GitHubError("invalid queued Actions response")
    count = payload.get("total_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise GitHubError("invalid queued Actions count")
    return count


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

    max_queued_actions = _int_env(
        "PR_AUTOMATION_MAX_QUEUED_ACTIONS_RUNS",
        40,
        minimum=0,
        maximum=100_000,
    )
    queued_actions = queued_actions_count(client, live_snapshot.repository)
    if queued_actions >= max_queued_actions:
        held = _operational_hold(
            live_snapshot,
            live_evaluation,
            (
                "Actions queue pressure blocks automated merge: "
                f"{queued_actions} queued >= {max_queued_actions}"
            ),
        )
        index.append(
            snapshot=live_snapshot,
            evaluation=held,
            event_type="actions_queue_pressure",
            delivery_id=f"{delivery_id}:queue-pressure" if delivery_id else None,
            extra={
                "queued_actions_runs": queued_actions,
                "threshold": max_queued_actions,
            },
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


def canonical_commit_oid(value: str) -> str:
    """Return a lowercase 40-hex Git commit OID, or fail closed.

    Privileged workflow_run identity must be an immutable full SHA. Whitespace,
    abbreviations, and non-hex values are rejected so they cannot degrade into
    an ambiguous commits/history lookup.
    """
    if not isinstance(value, str):
        raise GitHubError("workflow_run head SHA must be a 40-character hex commit OID")
    oid = value.casefold()
    if COMMIT_OID_RE.fullmatch(oid) is None:
        raise GitHubError("workflow_run head SHA must be a 40-character hex commit OID")
    return oid


def list_open_prs(client: GitHubClient, repository: str, limit: int) -> list[int]:
    owner, name = repository.split("/", 1)
    limit = min(max(1, limit), 1000)
    payload, _complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/pulls?state=open&sort=updated&direction=desc",
        max_pages=max(1, (limit + 99) // 100),
    )
    return [int(pr["number"]) for pr in payload[:limit]]


def _pr_number(item: Any) -> int:
    try:
        return int((item or {}).get("number") or 0)
    except (TypeError, ValueError):
        return 0


def parse_pr_hints_json(raw: str) -> list[int]:
    """Parse GitHub's workflow_run.pull_requests numbers from env JSON.

    The event array is capped and often empty; hints never replace SHA/branch
    identity. Fail closed on malformed payloads so a truncated expression cannot
    silently evaluate the wrong PR.
    """
    text = (raw or "").strip()
    if not text or text in {"null", "[]"}:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GitHubError("invalid workflow_run PR hint JSON") from exc
    if not isinstance(payload, list):
        raise GitHubError("workflow_run PR hints must be a JSON array")
    numbers: dict[int, None] = {}
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise GitHubError(f"invalid workflow_run PR hint: {item!r}")
        numbers[item] = None
    return list(numbers)


def _same_repo_head(pr: dict[str, Any], repository: str, head_ref: str) -> bool:
    head = pr.get("head") or {}
    head_repo = str(((head.get("repo") or {}).get("full_name") or ""))
    return (
        bool(head_repo)
        and head_repo.casefold() == repository.casefold()
        and str(head.get("ref") or "") == head_ref
    )


def resolve_branch_completion_prs(
    client: GitHubClient,
    *,
    repository: str,
    head_sha: str,
    head_ref: str,
    allowed_bases: tuple[str, ...],
    hinted_numbers: list[int] | None = None,
) -> list[int]:
    """Return every trusted PR associated with a completed workflow branch.

    GitHub's ``workflow_run.pull_requests`` array is often empty, capped at ten
    entries, and only populated for some triggering events. Completions on
    feature branches must therefore be resolved from the immutable head SHA
    plus branch name so every associated same-repository PR is evaluated.
    """
    if not repository or repository.count("/") != 1:
        raise GitHubError("incomplete repository identity for branch completion")
    if not head_sha or not head_ref:
        raise GitHubError("workflow_run completions require both head SHA and branch")
    head_sha = canonical_commit_oid(head_sha)
    allowed = {base.casefold() for base in allowed_bases if base}
    if not allowed:
        raise GitHubError("allowed bases are required to resolve branch completions")

    owner, name = repository.split("/", 1)
    ordered: dict[int, None] = {}

    def consider(pr: Any) -> None:
        if not isinstance(pr, dict):
            return
        number = _pr_number(pr)
        if number <= 0 or not _same_repo_head(pr, repository, head_ref):
            return
        base_ref = str((pr.get("base") or {}).get("ref") or "")
        if base_ref.casefold() not in allowed:
            return
        ordered[number] = None

    for hinted in hinted_numbers or []:
        if hinted <= 0:
            raise GitHubError(f"invalid hinted PR number: {hinted}")
        payload = client.get(f"/repos/{owner}/{name}/pulls/{hinted}")
        if not isinstance(payload, dict):
            raise GitHubError(f"invalid hinted PR #{hinted} response")
        consider(payload)

    quoted_sha = quote(head_sha, safe="")
    associated, associated_complete = _paged_list(
        client,
        f"/repos/{owner}/{name}/commits/{quoted_sha}/pulls",
    )
    if not associated_complete:
        raise GitHubError("commit PR association exceeded bounded identity scan")
    for item in associated:
        consider(item)

    if not ordered:
        query = urlencode(
            {
                "state": "all",
                "head": f"{owner}:{head_ref}",
                "sort": "updated",
                "direction": "desc",
            }
        )
        history, history_complete = _paged_list(
            client,
            f"/repos/{owner}/{name}/pulls?{query}",
        )
        if not history_complete:
            raise GitHubError("workflow_run branch history exceeded bounded identity scan")
        for item in history:
            recorded_sha = str(((item or {}).get("head") or {}).get("sha") or "")
            try:
                if canonical_commit_oid(recorded_sha) == head_sha:
                    consider(item)
            except GitHubError:
                continue

    return list(ordered)


def select_evaluation_targets(
    client: GitHubClient,
    *,
    repository: str,
    explicit_pr: int | None,
    head_sha: str,
    head_ref: str,
    default_branch: str,
    allowed_bases: tuple[str, ...],
    hinted_numbers: list[int],
    limit: int,
) -> list[int]:
    """Choose PRs for one automation run from explicit, completion, or sweep input."""
    if explicit_pr is not None:
        return [explicit_pr]
    if head_sha or head_ref:
        if not head_sha or not head_ref:
            raise GitHubError("workflow_run completions require both head SHA and branch")
        head_sha = canonical_commit_oid(head_sha)
        if default_branch and head_ref == default_branch:
            return list_open_prs(client, repository, limit)
        return resolve_branch_completion_prs(
            client,
            repository=repository,
            head_sha=head_sha,
            head_ref=head_ref,
            allowed_bases=allowed_bases,
            hinted_numbers=hinted_numbers,
        )
    return list_open_prs(client, repository, limit)


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
        raw_sha = str((pr.get("head") or {}).get("sha") or "") if isinstance(pr, dict) else ""
        if not raw_sha:
            return
        head_sha = canonical_commit_oid(raw_sha)
        snapshot = PRSnapshot(
            repository=repository,
            number=number,
            head_sha=head_sha,
            base_sha="0" * 40,
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
    if _bool_env("PR_AUTOMATION_RUNNER_V2", False):
        from .runner_v2_cli import run_v2

        return run_v2(argv)

    parser = argparse.ArgumentParser(description="Evaluate and safely automate pull requests.")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int)
    parser.add_argument(
        "--pr-hint",
        dest="pr_hints",
        type=int,
        action="append",
        default=[],
        help="workflow_run pull_requests[] hint; never the sole identity source",
    )
    parser.add_argument(
        "--pr-hints-json",
        default=os.getenv("WORKFLOW_RUN_PR_HINTS", ""),
        help="JSON array of workflow_run.pull_requests[].number hints",
    )
    parser.add_argument("--head-sha", default=os.getenv("WORKFLOW_RUN_HEAD_SHA", ""))
    parser.add_argument("--head-ref", default=os.getenv("WORKFLOW_RUN_HEAD_REF", ""))
    parser.add_argument(
        "--default-branch",
        default=os.getenv("DEFAULT_BRANCH", "") or os.getenv("GITHUB_REF_NAME", ""),
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--index", default=os.getenv("PR_AUTOMATION_INDEX", ".pr-automation/index.sqlite3"))
    parser.add_argument("--export", default=os.getenv("PR_AUTOMATION_EXPORT", ".pr-automation/index.jsonl"))
    args = parser.parse_args(argv)

    if not args.repo or args.repo.count("/") != 1:
        parser.error("--repo or GITHUB_REPOSITORY must be owner/name")
    if args.pr is not None and args.pr <= 0:
        parser.error("--pr must be positive")
    if any(hint <= 0 for hint in args.pr_hints):
        parser.error("--pr-hint must be positive")
    try:
        json_hints = parse_pr_hints_json(str(args.pr_hints_json or ""))
    except GitHubError as exc:
        parser.error(str(exc))
    hinted_numbers = list(dict.fromkeys([*json_hints, *args.pr_hints]))
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    if bool(args.head_sha) != bool(args.head_ref) and args.pr is None:
        parser.error("workflow_run completions require both --head-sha and --head-ref")

    safety = load_operator_safety()
    if safety.blocked:
        print(
            json.dumps(
                {
                    "kind": "pr-automation-operator-hold",
                    **safety.public_payload(),
                },
                sort_keys=True,
            )
        )
        return 0

    admission = None
    if args.head_sha and args.head_ref:
        event = event_from_env(
            os.environ,
            repository=args.repo,
            head_sha=str(args.head_sha),
            head_branch=str(args.head_ref),
            pr_hints_json=str(args.pr_hints_json or ""),
        )
        admission = admit_workflow_run(event)
        if admission.dropped:
            print(
                json.dumps(
                    {
                        "kind": "pr-automation-event-admission",
                        **admission.public_payload(),
                    },
                    sort_keys=True,
                )
            )
            return 0

    mode = Mode(os.getenv("PR_AUTOMATION_MODE", "observe").casefold())
    if admission is not None and not admission.mutation_authorized:
        mode = Mode.OBSERVE

    token = os.getenv("GITHUB_TOKEN", "")
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
    numbers = select_evaluation_targets(
        client,
        repository=args.repo,
        explicit_pr=args.pr,
        head_sha=str(args.head_sha or ""),
        head_ref=str(args.head_ref or ""),
        default_branch=str(args.default_branch or ""),
        allowed_bases=policy.allowed_bases,
        hinted_numbers=hinted_numbers,
        limit=args.limit,
    )
    if not numbers:
        print(
            "no trusted pull requests associated with the completing branch",
            file=sys.stderr,
        )
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
