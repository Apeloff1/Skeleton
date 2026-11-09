"""Exact-head workflow and review evidence aggregation for auto-merge.

The aggregator deliberately ignores convenient but unsafe shortcuts such as
"overall combined status".  It selects the newest attempt for each named
workflow on the exact pull-request head SHA, distinguishes cancellation from
failure, and records missing evidence explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from .automerge_model import (
    GateRequirement,
    GateResult,
    GateState,
    ReviewEvidence,
    WorkflowEvidence,
    parse_timestamp,
)


TERMINAL_FAILURE_CONCLUSIONS = frozenset(
    {
        "failure",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
)
PENDING_STATUSES = frozenset(
    {"queued", "in_progress", "pending", "requested", "waiting"}
)


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    approvals: int
    changes_requested: int
    latest_states: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    gates: tuple[GateResult, ...]
    approvals: int
    changes_requested: int
    unresolved_threads: int | None

    @property
    def all_required_successful(self) -> bool:
        return all(item.state is GateState.SUCCESS for item in self.gates)

    @property
    def pending(self) -> bool:
        return any(item.state is GateState.PENDING for item in self.gates)

    @property
    def missing(self) -> bool:
        return any(item.state is GateState.MISSING for item in self.gates)

    @property
    def failed(self) -> bool:
        return any(
            item.state
            in {
                GateState.FAILURE,
                GateState.CANCELLED,
                GateState.UNKNOWN,
            }
            for item in self.gates
        )


def _workflow_rank(run: WorkflowEvidence) -> tuple[int, int, datetime]:
    updated = parse_timestamp(run.updated_at) or parse_timestamp(run.created_at)
    if updated is None:
        updated = datetime.min.replace(tzinfo=timezone.utc)
    return (run.run_number, run.attempt, updated)


def latest_exact_head_runs(
    runs: Iterable[WorkflowEvidence],
    *,
    head_sha: str,
    event: str | None = "pull_request",
) -> dict[str, WorkflowEvidence]:
    latest: dict[str, WorkflowEvidence] = {}
    for run in runs:
        if run.head_sha != head_sha:
            continue
        if event is not None and run.event != event:
            continue
        prior = latest.get(run.name)
        if prior is None or _workflow_rank(run) >= _workflow_rank(prior):
            latest[run.name] = run
    return latest


def aggregate_required_workflows(
    runs: Iterable[WorkflowEvidence],
    requirements: Sequence[GateRequirement],
    *,
    head_sha: str,
) -> tuple[GateResult, ...]:
    exact_pr = latest_exact_head_runs(runs, head_sha=head_sha, event="pull_request")
    exact_any = latest_exact_head_runs(runs, head_sha=head_sha, event=None)
    results: list[GateResult] = []

    for requirement in requirements:
        source = exact_pr if requirement.require_pull_request_event else exact_any
        run = source.get(requirement.name)
        if run is None:
            results.append(
                GateResult(
                    name=requirement.name,
                    state=GateState.MISSING,
                    run_id=None,
                    reason="no exact-head workflow evidence",
                )
            )
            continue

        state = run.state()
        if state is GateState.SKIPPED and requirement.allow_skipped:
            state = GateState.SUCCESS
            reason = "latest exact-head run skipped under explicit policy"
        elif state is GateState.SUCCESS:
            reason = "latest exact-head workflow attempt succeeded"
        elif state is GateState.PENDING:
            reason = "latest exact-head workflow attempt is still pending"
        elif state is GateState.CANCELLED:
            reason = "latest exact-head workflow attempt was cancelled"
        elif state is GateState.SKIPPED:
            reason = "latest exact-head workflow attempt was skipped"
        elif state is GateState.FAILURE:
            reason = "latest exact-head workflow attempt failed"
        else:
            reason = "latest exact-head workflow attempt has unknown terminal state"

        results.append(
            GateResult(
                name=requirement.name,
                state=state,
                run_id=run.run_id,
                reason=reason,
            )
        )

    return tuple(results)


def latest_reviews_by_user(
    reviews: Iterable[ReviewEvidence],
) -> dict[str, ReviewEvidence]:
    result: dict[str, ReviewEvidence] = {}
    for review in reviews:
        login = review.login.casefold().strip()
        if not login:
            continue
        state = review.normalized_state()
        if state == "COMMENTED":
            continue
        prior = result.get(login)
        if prior is None:
            result[login] = review
            continue
        prior_time = parse_timestamp(prior.submitted_at)
        current_time = parse_timestamp(review.submitted_at)
        if prior_time is None and current_time is not None:
            result[login] = review
        elif current_time is not None and prior_time is not None and current_time >= prior_time:
            result[login] = review
        elif current_time is None and prior_time is None:
            result[login] = review
    return result


def summarize_reviews(reviews: Iterable[ReviewEvidence]) -> ReviewSummary:
    latest = latest_reviews_by_user(reviews)
    approvals = 0
    changes_requested = 0
    states: list[tuple[str, str]] = []
    for login, review in sorted(latest.items()):
        state = review.normalized_state()
        states.append((login, state))
        if state == "APPROVED":
            approvals += 1
        elif state == "CHANGES_REQUESTED":
            changes_requested += 1
    return ReviewSummary(
        approvals=approvals,
        changes_requested=changes_requested,
        latest_states=tuple(states),
    )


def summarize_evidence(
    *,
    runs: Iterable[WorkflowEvidence],
    requirements: Sequence[GateRequirement],
    head_sha: str,
    reviews: Iterable[ReviewEvidence],
    unresolved_threads: int | None,
) -> EvidenceSummary:
    review = summarize_reviews(reviews)
    gates = aggregate_required_workflows(
        runs,
        requirements,
        head_sha=head_sha,
    )
    return EvidenceSummary(
        gates=gates,
        approvals=review.approvals,
        changes_requested=review.changes_requested,
        unresolved_threads=unresolved_threads,
    )


def stale_successes(
    runs: Iterable[WorkflowEvidence],
    *,
    required_names: Sequence[str],
    head_sha: str,
) -> tuple[WorkflowEvidence, ...]:
    """Return successful required runs that belong to another head.

    This is diagnostic evidence only.  A stale success can never satisfy an
    exact-head requirement, but surfacing it makes queue pressure and cancelled
    reruns much easier to diagnose.
    """
    required = set(required_names)
    latest_by_name_and_head: dict[tuple[str, str], WorkflowEvidence] = {}
    for run in runs:
        if run.name not in required or run.event != "pull_request":
            continue
        key = (run.name, run.head_sha)
        prior = latest_by_name_and_head.get(key)
        if prior is None or _workflow_rank(run) >= _workflow_rank(prior):
            latest_by_name_and_head[key] = run

    stale = [
        run
        for (name, sha), run in latest_by_name_and_head.items()
        if sha != head_sha and run.state() is GateState.SUCCESS and name in required
    ]
    stale.sort(key=lambda item: (item.name, item.head_sha, item.run_number, item.attempt))
    return tuple(stale)


def duplicate_attempts(
    runs: Iterable[WorkflowEvidence],
    *,
    head_sha: str,
) -> Mapping[str, tuple[WorkflowEvidence, ...]]:
    groups: dict[str, list[WorkflowEvidence]] = defaultdict(list)
    for run in runs:
        if run.head_sha == head_sha and run.event == "pull_request":
            groups[run.name].append(run)
    duplicates: dict[str, tuple[WorkflowEvidence, ...]] = {}
    for name, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=_workflow_rank)
        duplicates[name] = tuple(items)
    return duplicates


def workflow_state_counts(
    runs: Iterable[WorkflowEvidence],
    *,
    head_sha: str,
) -> dict[GateState, int]:
    counts = {state: 0 for state in GateState}
    latest = latest_exact_head_runs(runs, head_sha=head_sha, event="pull_request")
    for run in latest.values():
        counts[run.state()] += 1
    return counts


def evidence_complete(
    summary: EvidenceSummary,
    *,
    required_approvals: int,
    require_no_changes_requested: bool,
    require_resolved_threads: bool,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    for gate in summary.gates:
        if gate.state is not GateState.SUCCESS:
            reasons.append(f"gate:{gate.name}:{gate.state.value}")
    if summary.approvals < required_approvals:
        reasons.append(
            f"approvals:{summary.approvals}:required:{required_approvals}"
        )
    if require_no_changes_requested and summary.changes_requested:
        reasons.append(f"changes_requested:{summary.changes_requested}")
    if require_resolved_threads:
        if summary.unresolved_threads is None:
            reasons.append("review_threads:unknown")
        elif summary.unresolved_threads:
            reasons.append(
                f"review_threads:unresolved:{summary.unresolved_threads}"
            )
    return (not reasons, tuple(reasons))


def explain_gate_results(gates: Sequence[GateResult]) -> tuple[str, ...]:
    return tuple(
        f"{gate.name}={gate.state.value} ({gate.reason})"
        for gate in gates
    )


def required_names(requirements: Sequence[GateRequirement]) -> tuple[str, ...]:
    return tuple(item.name for item in requirements)


def newest_success_timestamp(
    runs: Iterable[WorkflowEvidence],
    *,
    head_sha: str,
    required_names: Sequence[str],
) -> datetime | None:
    latest = latest_exact_head_runs(runs, head_sha=head_sha, event="pull_request")
    timestamps: list[datetime] = []
    for name in required_names:
        run = latest.get(name)
        if run is None or run.state() is not GateState.SUCCESS:
            return None
        timestamp = parse_timestamp(run.updated_at) or parse_timestamp(run.created_at)
        if timestamp is None:
            return None
        timestamps.append(timestamp)
    return max(timestamps) if timestamps else None


def stability_elapsed(
    runs: Iterable[WorkflowEvidence],
    *,
    head_sha: str,
    required_names: Sequence[str],
    now: datetime,
    stability_seconds: int,
) -> bool:
    newest = newest_success_timestamp(
        runs,
        head_sha=head_sha,
        required_names=required_names,
    )
    if newest is None:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now.astimezone(timezone.utc) - newest
    return delta.total_seconds() >= stability_seconds


__all__ = [
    "EvidenceSummary",
    "ReviewSummary",
    "aggregate_required_workflows",
    "duplicate_attempts",
    "evidence_complete",
    "explain_gate_results",
    "latest_exact_head_runs",
    "latest_reviews_by_user",
    "newest_success_timestamp",
    "required_names",
    "stability_elapsed",
    "stale_successes",
    "summarize_evidence",
    "summarize_reviews",
    "workflow_state_counts",
]
