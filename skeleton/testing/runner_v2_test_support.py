"""Shared fixtures for the PR automation runner-v2 regression suites."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Mapping

from skeleton.pr_automation.core import (
    CIState,
    Decision,
    Evaluation,
    Mode,
    PRSnapshot,
    PlannedAction,
    Policy,
)
from skeleton.pr_automation.runner_contracts import (
    AdmissionDecision,
    AdmissionState,
    CheckEvidence,
    CheckState,
    EvidenceCompleteness,
    FileEvidence,
    PriorityBand,
    ReviewEvidence,
    RunIdentity,
    RunnerLimits,
    RunnerPolicy,
    RunnerSnapshot,
    RunTrigger,
    Target,
    WorkItem,
    WorkState,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
BASE_CHECKS = ("Merge Readiness", "CI/CD")


def limits(**changes: Any) -> RunnerLimits:
    base = RunnerLimits(
        max_targets=25,
        max_requests=500,
        max_graphql_requests=100,
        max_mutations=2,
        max_pages=10,
        max_response_bytes=1024 * 1024,
        max_changed_files=250,
        max_events_exported=10_000,
        deadline_seconds=600,
        per_target_request_budget=100,
        queue_pressure_threshold=40,
        minimum_rate_remaining=10,
        retry_attempts=2,
        retry_ceiling_seconds=5,
    )
    return replace(base, **changes)


def core_policy(**changes: Any) -> Policy:
    base = Policy(
        allowed_bases=("main",),
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
        require_checks=True,
        allow_fork_merge=False,
        max_changed_files=250,
        max_total_line_delta=20_000,
        merge_when_ready=True,
    )
    return replace(base, **changes)


def runner_policy(**changes: Any) -> RunnerPolicy:
    base = RunnerPolicy(
        core=core_policy(),
        mode=Mode.APPLY,
        required_checks=BASE_CHECKS,
        merge_method="squash",
        protected_base_required=True,
        exact_base_head_required=True,
        queue_pressure_hold=True,
        publish_gate_status=True,
        require_same_repository_head=True,
        require_latest_reviews_on_head=True,
        limits=limits(),
    )
    return replace(base, **changes)


def identity(**changes: Any) -> RunIdentity:
    base = RunIdentity(
        repository="Apeloff1/Skeleton",
        delivery_id="12345",
        trigger=RunTrigger.EXPLICIT,
        default_branch="main",
        explicit_pr=42,
    )
    return replace(base, **changes)


def admission(**changes: Any) -> AdmissionDecision:
    base = AdmissionDecision(
        state=AdmissionState.ADMIT,
        reasons=("admitted",),
        mutation_authorized=True,
        priority=PriorityBand.INTERACTIVE,
        identity_fingerprint=identity().fingerprint(),
    )
    return replace(base, **changes)


def check(
    name: str,
    *,
    state: CheckState = CheckState.PASSING,
    provider: str = "github-actions:15368",
    source: str = "check_run",
    source_id: int = 1,
    head_sha: str = SHA_B,
    updated_at: datetime | None = None,
) -> CheckEvidence:
    when = updated_at or (NOW - timedelta(minutes=5))
    return CheckEvidence(
        name=name,
        provider=provider,
        state=state,
        source=source,
        source_id=source_id,
        head_sha=head_sha,
        started_at=(when - timedelta(minutes=1)).isoformat(),
        completed_at=when.isoformat(),
        updated_at=when.isoformat(),
        details_url=f"https://example.invalid/{source_id}",
    )


def review(
    login: str = "reviewer",
    *,
    state: str = "APPROVED",
    review_id: int = 1,
    commit_id: str | None = SHA_B,
    submitted_at: datetime | None = None,
) -> ReviewEvidence:
    return ReviewEvidence(
        login=login,
        state=state,
        review_id=review_id,
        commit_id=commit_id,
        submitted_at=(submitted_at or NOW - timedelta(minutes=10)).isoformat(),
    )


def changed_file(
    filename: str = "docs/example.md",
    *,
    status: str = "modified",
    additions: int = 5,
    deletions: int = 1,
    changes: int | None = None,
    previous_filename: str | None = None,
) -> FileEvidence:
    return FileEvidence(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        changes=changes if changes is not None else additions + deletions,
        previous_filename=previous_filename,
    )


def core_snapshot(**changes: Any) -> PRSnapshot:
    base = PRSnapshot(
        repository="Apeloff1/Skeleton",
        number=42,
        head_sha=SHA_B,
        base_sha=SHA_A,
        base_ref="main",
        head_ref="feature/runner-v2",
        state="open",
        merged=False,
        draft=False,
        from_fork=False,
        mergeable=True,
        mergeable_state="clean",
        ci_state=CIState.PASSING,
        approvals=0,
        changes_requested=0,
        unresolved_threads=0,
        changed_files=1,
        additions=5,
        deletions=1,
        sensitive_paths=(),
        labels=("automerge",),
        updated_at=(NOW - timedelta(minutes=20)).isoformat(),
    )
    return replace(base, **changes)


def complete(**changes: Any) -> EvidenceCompleteness:
    base = EvidenceCompleteness(
        pull_request=True,
        checks=True,
        statuses=True,
        reviews=True,
        threads=True,
        files=True,
        base_branch=True,
        base_head=True,
    )
    return replace(base, **changes)


def snapshot(**changes: Any) -> RunnerSnapshot:
    core = changes.pop("core", core_snapshot())
    files = changes.pop("files", (changed_file(),))
    checks = changes.pop(
        "checks",
        tuple(
            check(name, source_id=index + 1)
            for index, name in enumerate(BASE_CHECKS)
        ),
    )
    reviews = changes.pop("reviews", ())
    check_states = changes.pop(
        "required_check_states",
        tuple((name, CheckState.PASSING) for name in BASE_CHECKS),
    )
    base = RunnerSnapshot(
        core=core,
        pr_node_id="PR_runner_v2_42",
        author="Apeloff1",
        head_repository="Apeloff1/Skeleton",
        base_head_sha=SHA_A,
        labels=core.labels,
        files=files,
        checks=checks,
        reviews=reviews,
        required_check_states=check_states,
        completeness=complete(),
        captured_at=NOW.isoformat(),
        source_request_count=8,
        etag=None,
    )
    return replace(base, **changes)


def target(**changes: Any) -> Target:
    base = Target(
        number=42,
        reason="explicit_pr",
        priority=PriorityBand.INTERACTIVE,
        hinted=False,
        associated_by_sha=False,
        associated_by_branch=False,
    )
    return replace(base, **changes)


def evaluation(
    snap: RunnerSnapshot | None = None,
    *,
    decision: Decision = Decision.MERGE,
    reasons: tuple[str, ...] = ("all policy gates satisfied",),
) -> Evaluation:
    current = snap or snapshot()
    actions = ()
    if decision is Decision.MERGE:
        actions = (
            PlannedAction.make(
                current.core,
                "merge",
                "all policy gates satisfied",
            ),
        )
    return Evaluation(
        decision=decision,
        reasons=reasons,
        actions=actions,
        snapshot_fingerprint=current.core.fingerprint(),
        policy_fingerprint=core_policy().fingerprint(),
    )


def work_item(
    snap: RunnerSnapshot | None = None,
    *,
    item_target: Target | None = None,
    item_evaluation: Evaluation | None = None,
    state: WorkState = WorkState.READY,
    score: int = 50_000,
) -> WorkItem:
    current = snap or snapshot()
    ev = item_evaluation or evaluation(current)
    return WorkItem(
        target=item_target or target(),
        snapshot=current,
        evaluation=ev,
        state=state,
        score=score,
        reasons=ev.reasons,
        observed_queue_depth=0,
        observed_rate_remaining=5000,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )


def pr_payload(
    *,
    number: int = 42,
    head_sha: str = SHA_B,
    base_sha: str = SHA_A,
    base_ref: str = "main",
    head_ref: str = "feature/runner-v2",
    head_repo: str | None = "Apeloff1/Skeleton",
    author: str = "Apeloff1",
    draft: bool = False,
    merged: bool = False,
    state: str = "open",
    mergeable: bool | None = True,
    mergeable_state: str = "clean",
    labels: tuple[str, ...] = ("automerge",),
    changed_files: int = 1,
    additions: int = 5,
    deletions: int = 1,
) -> dict[str, Any]:
    return {
        "id": 123,
        "node_id": f"PR_node_{number}",
        "number": number,
        "state": state,
        "merged": merged,
        "draft": draft,
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "head": {
            "sha": head_sha,
            "ref": head_ref,
            "repo": (
                {"full_name": head_repo}
                if head_repo is not None
                else None
            ),
        },
        "base": {
            "sha": base_sha,
            "ref": base_ref,
        },
        "user": {"login": author},
        "labels": [{"name": value} for value in labels],
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "updated_at": (NOW - timedelta(minutes=20)).isoformat(),
    }


def check_run_payload(
    name: str,
    *,
    state: str = "success",
    status: str = "completed",
    run_id: int = 1,
    head_sha: str = SHA_B,
    app_slug: str = "github-actions",
    app_id: int = 15368,
    when: datetime | None = None,
) -> dict[str, Any]:
    moment = when or (NOW - timedelta(minutes=5))
    return {
        "id": run_id,
        "name": name,
        "head_sha": head_sha,
        "status": status,
        "conclusion": state,
        "app": {"slug": app_slug, "id": app_id},
        "started_at": (moment - timedelta(minutes=1)).isoformat(),
        "completed_at": moment.isoformat() if status == "completed" else None,
        "updated_at": moment.isoformat(),
        "details_url": f"https://example.invalid/run/{run_id}",
    }


def status_payload(
    context: str,
    *,
    state: str = "success",
    status_id: int = 1,
    creator: str = "github-actions",
    when: datetime | None = None,
) -> dict[str, Any]:
    moment = when or (NOW - timedelta(minutes=5))
    return {
        "id": status_id,
        "context": context,
        "state": state,
        "creator": {"login": creator, "id": 99},
        "created_at": (moment - timedelta(seconds=10)).isoformat(),
        "updated_at": moment.isoformat(),
        "target_url": f"https://example.invalid/status/{status_id}",
    }


def review_payload(
    *,
    login: str = "reviewer",
    state: str = "APPROVED",
    review_id: int = 1,
    commit_id: str | None = SHA_B,
    when: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": review_id,
        "user": {"login": login},
        "state": state,
        "commit_id": commit_id,
        "submitted_at": (when or NOW - timedelta(minutes=10)).isoformat(),
    }


def file_payload(
    filename: str = "docs/example.md",
    *,
    status: str = "modified",
    additions: int = 5,
    deletions: int = 1,
    changes: int | None = None,
    previous_filename: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "changes": changes if changes is not None else additions + deletions,
    }
    if previous_filename is not None:
        payload["previous_filename"] = previous_filename
    return payload


def branch_payload(
    *,
    sha: str = SHA_A,
    protected: bool = True,
) -> dict[str, Any]:
    return {
        "name": "main",
        "protected": protected,
        "commit": {"sha": sha},
    }


def threads_payload(
    *,
    unresolved: int = 0,
    resolved: int = 0,
    has_next: bool = False,
    cursor: str | None = None,
) -> dict[str, Any]:
    nodes = [
        {"isResolved": False, "isOutdated": False}
        for _ in range(unresolved)
    ] + [
        {"isResolved": True, "isOutdated": False}
        for _ in range(resolved)
    ]
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": cursor,
                    },
                }
            }
        }
    }


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if isinstance(payload, bytes):
            self._data = payload
        elif payload is None:
            self._data = b""
        else:
            self._data = json.dumps(payload).encode("utf-8")
        self.status = status
        self.headers = dict(headers or {})

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            return self._data
        return self._data[:amount]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class RouteOpener:
    """Minimal urllib opener fixture keyed by (method, absolute URL)."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list[Any]] = {}
        self.calls: list[tuple[str, str, bytes | None]] = []

    def add(
        self,
        method: str,
        url: str,
        *responses: Any,
    ) -> None:
        self.routes.setdefault((method.upper(), url), []).extend(responses)

    def __call__(self, request: Any, timeout: int = 30) -> Any:
        method = request.get_method().upper()
        url = request.full_url
        body = request.data
        self.calls.append((method, url, body))
        key = (method, url)
        queue = self.routes.get(key)
        if not queue:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = queue.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class ScriptedTransport:
    """Transport fixture for EvidenceCollector/TargetResolver/transaction tests."""

    def __init__(self) -> None:
        self.request_count = 0
        self.minimum_rate_remaining: int | None = 5000
        self.get_map: dict[str, Any] = {}
        self.list_map: dict[str, tuple[list[Mapping[str, Any]], bool]] = {}
        self.named_map: dict[
            tuple[str, str],
            tuple[list[Mapping[str, Any]], bool],
        ] = {}
        self.graphql_queue: list[Mapping[str, Any]] = []
        self.put_map: dict[str, Any] = {}
        self.post_map: dict[str, Any] = {}
        self.put_calls: list[tuple[str, Mapping[str, Any] | None]] = []
        self.post_calls: list[tuple[str, Mapping[str, Any] | None]] = []

    def get(self, path: str) -> Any:
        self.request_count += 1
        if path not in self.get_map:
            raise AssertionError(f"unexpected GET {path}")
        value = self.get_map[path]
        if isinstance(value, BaseException):
            raise value
        return value

    def paged_list(
        self,
        path: str,
        *,
        max_pages: int | None = None,
        per_page: int = 100,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        self.request_count += 1
        if path not in self.list_map:
            raise AssertionError(f"unexpected paged_list {path}")
        return self.list_map[path]

    def paged_named_list(
        self,
        path: str,
        key: str,
        *,
        total_key: str | None = "total_count",
        max_pages: int | None = None,
        per_page: int = 100,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        self.request_count += 1
        pair = (path, key)
        if pair not in self.named_map:
            raise AssertionError(f"unexpected paged_named_list {pair}")
        return self.named_map[pair]

    def graphql(
        self,
        query: str,
        variables: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.request_count += 1
        if not self.graphql_queue:
            raise AssertionError("unexpected GraphQL call")
        return self.graphql_queue.pop(0)

    def put(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> Any:
        self.request_count += 1
        self.put_calls.append((path, body))
        if path not in self.put_map:
            raise AssertionError(f"unexpected PUT {path}")
        value = self.put_map[path]
        if isinstance(value, BaseException):
            raise value
        return value

    def post(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> Any:
        self.request_count += 1
        self.post_calls.append((path, body))
        return self.post_map.get(path, {})

    def queued_actions_count(self, repository: str) -> int:
        self.request_count += 1
        key = f"queue:{repository}"
        value = self.get_map.get(key, 0)
        if isinstance(value, BaseException):
            raise value
        return int(value)

    def summary(self, *, include_records: bool = True):
        from skeleton.pr_automation.runner_contracts import TransportSummary

        return TransportSummary(
            requests=self.request_count,
            graphql_requests=0,
            retries=0,
            bytes_received=0,
            rate_limited=0,
            failures=0,
            minimum_remaining_seen=self.minimum_rate_remaining,
            records=(),
        )


def configure_collector_transport(
    transport: ScriptedTransport,
    *,
    repository: str = "Apeloff1/Skeleton",
    number: int = 42,
    pr: Mapping[str, Any] | None = None,
    checks: tuple[Mapping[str, Any], ...] | None = None,
    statuses: tuple[Mapping[str, Any], ...] = (),
    reviews: tuple[Mapping[str, Any], ...] = (),
    files: tuple[Mapping[str, Any], ...] | None = None,
    unresolved: int = 0,
    base: Mapping[str, Any] | None = None,
) -> ScriptedTransport:
    current_pr = dict(pr or pr_payload(number=number))
    head_sha = str(current_pr["head"]["sha"])
    base_ref = str(current_pr["base"]["ref"])
    current_checks = checks or tuple(
        check_run_payload(name, run_id=index + 1, head_sha=head_sha)
        for index, name in enumerate(BASE_CHECKS)
    )
    current_files = files or (file_payload(),)
    transport.get_map[f"/repos/{repository}/pulls/{number}"] = current_pr
    transport.named_map[
        (f"/repos/{repository}/commits/{head_sha}/check-runs", "check_runs")
    ] = (list(current_checks), True)
    transport.list_map[
        f"/repos/{repository}/commits/{head_sha}/statuses"
    ] = (list(statuses), True)
    transport.list_map[
        f"/repos/{repository}/pulls/{number}/reviews"
    ] = (list(reviews), True)
    transport.list_map[
        f"/repos/{repository}/pulls/{number}/files"
    ] = (list(current_files), True)
    transport.graphql_queue.append(threads_payload(unresolved=unresolved))
    transport.get_map[f"/repos/{repository}/branches/{base_ref}"] = dict(
        base or branch_payload(sha=str(current_pr["base"]["sha"]))
    )
    return transport
