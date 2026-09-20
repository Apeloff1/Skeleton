"""Deterministic scheduling, prioritization, and run-budget accounting.

Runner v2 evaluates targets independently but does not treat every ready pull
request as equally urgent.  This module translates immutable target/evidence
state into bounded work ordering while preserving fairness and making every
defer decision explicit.

The scheduler never mutates GitHub.  It is pure with respect to repository
state except for the caller-provided queue/rate observations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from .core import Decision, Evaluation, evaluate
from .runner_contracts import (
    AdmissionDecision,
    PriorityBand,
    RunBudget,
    RunnerPolicy,
    RunnerReason,
    RunnerSnapshot,
    Target,
    WorkItem,
    WorkState,
    parse_time,
    utcnow,
)
from .runner_evidence import (
    failing_required_checks,
    missing_required_checks,
    pending_required_checks,
    snapshot_incomplete_reasons,
    stale_reviewers,
)


_PRIORITY_SCORE = {
    PriorityBand.INTERACTIVE: 40_000,
    PriorityBand.COMPLETION: 30_000,
    PriorityBand.RECOVERY: 20_000,
    PriorityBand.SWEEP: 10_000,
}

_DECISION_SCORE = {
    Decision.MERGE: 5_000,
    Decision.READY: 4_000,
    Decision.HOLD: 2_000,
    Decision.IGNORE: 0,
}

_STATE_SCORE = {
    WorkState.READY: 2_000,
    WorkState.EVALUATED: 1_000,
    WorkState.HELD: 0,
    WorkState.IGNORED: -1_000,
    WorkState.DEFERRED: -2_000,
    WorkState.FAILED: -3_000,
}


@dataclass(frozen=True, slots=True)
class QueueObservation:
    queued_actions: int | None
    rate_remaining: int | None
    captured_at: str

    def __post_init__(self) -> None:
        if self.queued_actions is not None and self.queued_actions < 0:
            raise ValueError("queued_actions must be non-negative")
        if self.rate_remaining is not None and self.rate_remaining < 0:
            raise ValueError("rate_remaining must be non-negative")


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    reasons: tuple[str, ...]
    budget: RunBudget


@dataclass(frozen=True, slots=True)
class Schedule:
    items: tuple[WorkItem, ...]
    deferred: tuple[WorkItem, ...]
    created_at: str

    def all(self) -> tuple[WorkItem, ...]:
        return (*self.items, *self.deferred)


class MutableBudget:
    """Small controlled mutable counter around immutable `RunBudget` values."""

    def __init__(self, budget: RunBudget) -> None:
        self._budget = budget

    @property
    def value(self) -> RunBudget:
        return self._budget

    def _replace(self, **changes: int) -> RunBudget:
        self._budget = replace(self._budget, **changes)
        return self._budget

    def consume_request(self, count: int = 1) -> RunBudget:
        if type(count) is not int or count < 0:
            raise ValueError("request count must be a non-negative integer")
        value = self._budget.request_used + count
        if value > self._budget.request_limit:
            raise RuntimeError("request budget exceeded")
        return self._replace(request_used=value)

    def consume_graphql(self, count: int = 1) -> RunBudget:
        if type(count) is not int or count < 0:
            raise ValueError("GraphQL count must be a non-negative integer")
        value = self._budget.graphql_used + count
        if value > self._budget.graphql_limit:
            raise RuntimeError("GraphQL budget exceeded")
        return self._replace(graphql_used=value)

    def consume_mutation(self, count: int = 1) -> RunBudget:
        if type(count) is not int or count < 0:
            raise ValueError("mutation count must be a non-negative integer")
        value = self._budget.mutations_used + count
        if value > self._budget.mutation_limit:
            raise RuntimeError("mutation budget exceeded")
        return self._replace(mutations_used=value)

    def consume_target(self, count: int = 1) -> RunBudget:
        if type(count) is not int or count < 0:
            raise ValueError("target count must be a non-negative integer")
        value = self._budget.targets_used + count
        if value > self._budget.target_limit:
            raise RuntimeError("target budget exceeded")
        return self._replace(targets_used=value)


def make_budget(
    policy: RunnerPolicy,
    *,
    started_at: datetime | None = None,
) -> RunBudget:
    started = started_at or utcnow()
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    deadline = started.astimezone(timezone.utc) + timedelta(
        seconds=policy.limits.deadline_seconds
    )
    return RunBudget(
        request_limit=policy.limits.max_requests,
        graphql_limit=policy.limits.max_graphql_requests,
        mutation_limit=policy.limits.max_mutations,
        target_limit=policy.limits.max_targets,
        deadline_at=deadline.isoformat(),
    )


def deadline_reached(
    budget: RunBudget,
    *,
    now: datetime | None = None,
) -> bool:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc) >= budget.deadline()


def deadline_remaining_seconds(
    budget: RunBudget,
    *,
    now: datetime | None = None,
) -> int:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    remaining = budget.deadline() - moment.astimezone(timezone.utc)
    return max(0, int(remaining.total_seconds()))


def budget_allows_target(
    budget: RunBudget,
    *,
    estimated_requests: int,
    estimated_graphql: int,
    now: datetime | None = None,
) -> BudgetDecision:
    reasons: list[str] = []
    if deadline_reached(budget, now=now):
        reasons.append(RunnerReason.DEADLINE.value)
    if budget.remaining_targets() <= 0:
        reasons.append("target_budget_exhausted")
    if estimated_requests > budget.remaining_requests():
        reasons.append("request_budget_insufficient")
    if estimated_graphql > budget.remaining_graphql():
        reasons.append("graphql_budget_insufficient")
    return BudgetDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        budget=budget,
    )


def budget_allows_mutation(
    budget: RunBudget,
    observation: QueueObservation,
    policy: RunnerPolicy,
    *,
    now: datetime | None = None,
) -> BudgetDecision:
    reasons: list[str] = []
    if deadline_reached(budget, now=now):
        reasons.append(RunnerReason.DEADLINE.value)
    if budget.remaining_mutations() <= 0:
        reasons.append("mutation_budget_exhausted")
    if policy.queue_pressure_hold:
        if observation.queued_actions is None:
            reasons.append("queue_depth_unknown")
        elif observation.queued_actions > policy.limits.queue_pressure_threshold:
            reasons.append(RunnerReason.QUEUE_PRESSURE.value)
    if observation.rate_remaining is None:
        reasons.append("rate_limit_unknown")
    elif observation.rate_remaining < policy.limits.minimum_rate_remaining:
        reasons.append(RunnerReason.RATE_LIMIT.value)
    return BudgetDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        budget=budget,
    )


def evaluate_snapshot(
    snapshot: RunnerSnapshot,
    policy: RunnerPolicy,
) -> tuple[Evaluation, tuple[str, ...]]:
    reasons: list[str] = []

    if not snapshot.completeness.complete:
        reasons.extend(snapshot_incomplete_reasons(snapshot))

    if policy.require_same_repository_head and not snapshot.same_repository_head:
        reasons.append("head_repository_outside_policy")

    labels = {label.casefold() for label in snapshot.labels}
    denied = labels.intersection(policy.denied_labels)
    if denied:
        reasons.append("denied_label:" + ",".join(sorted(denied)))

    required = set(policy.required_labels)
    if required and not required.issubset(labels):
        missing = sorted(required.difference(labels))
        reasons.append("required_label_missing:" + ",".join(missing))

    if policy.allowed_authors:
        if snapshot.author.casefold() not in set(policy.allowed_authors):
            reasons.append("author_outside_policy")

    failed_checks = failing_required_checks(snapshot)
    pending_checks = pending_required_checks(snapshot)
    missing_checks = missing_required_checks(snapshot)
    if failed_checks:
        reasons.append("required_checks_failed:" + ",".join(failed_checks))
    if pending_checks:
        reasons.append("required_checks_pending:" + ",".join(pending_checks))
    if missing_checks:
        reasons.append("required_checks_missing:" + ",".join(missing_checks))

    if policy.require_latest_reviews_on_head:
        stale = stale_reviewers(snapshot)
        if stale:
            reasons.append("stale_approvals:" + ",".join(stale))

    if policy.exact_base_head_required and not snapshot.exact_base_head:
        reasons.append("base_head_mismatch")

    base = evaluate(snapshot.core, policy.core)
    if reasons:
        from .core import Evaluation as CoreEvaluation

        held = CoreEvaluation(
            decision=Decision.HOLD,
            reasons=tuple(reasons),
            actions=(),
            snapshot_fingerprint=snapshot.core.fingerprint(),
            policy_fingerprint=policy.core.fingerprint(),
        )
        return held, tuple(reasons)
    return base, tuple(base.reasons)


def work_state_for_evaluation(
    evaluation: Evaluation,
) -> WorkState:
    if evaluation.decision is Decision.MERGE:
        return WorkState.READY
    if evaluation.decision is Decision.READY:
        return WorkState.READY
    if evaluation.decision is Decision.HOLD:
        return WorkState.HELD
    if evaluation.decision is Decision.IGNORE:
        return WorkState.IGNORED
    return WorkState.EVALUATED


def recency_age_minutes(
    snapshot: RunnerSnapshot,
    *,
    now: datetime | None = None,
) -> int:
    updated = parse_time(snapshot.core.updated_at)
    if updated is None:
        return 0
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = moment.astimezone(timezone.utc) - updated
    if delta.total_seconds() < 0:
        return 0
    return int(delta.total_seconds() // 60)


def score_work_item(
    target: Target,
    snapshot: RunnerSnapshot,
    evaluation: Evaluation,
    state: WorkState,
    *,
    now: datetime | None = None,
) -> int:
    """Compute deterministic scheduling score.

    Higher scores run first.  Age contributes a bounded anti-starvation bonus,
    while smaller diffs receive a modest preference because they generally
    consume less mutation risk and CI fanout.
    """
    score = _PRIORITY_SCORE[target.priority]
    score += _DECISION_SCORE[evaluation.decision]
    score += _STATE_SCORE[state]

    age = min(24 * 60, recency_age_minutes(snapshot, now=now))
    score += age

    diff_penalty = min(
        2_000,
        snapshot.core.changed_files * 2
        + (snapshot.core.additions + snapshot.core.deletions) // 50,
    )
    score -= diff_penalty

    if target.hinted:
        score += 50
    if target.associated_by_sha:
        score += 100
    if snapshot.core.sensitive_paths:
        score -= min(1_000, 100 * len(snapshot.core.sensitive_paths))
    if snapshot.core.from_fork:
        score -= 2_000
    return max(-1_000_000, min(1_000_000, score))


def build_work_item(
    target: Target,
    snapshot: RunnerSnapshot,
    policy: RunnerPolicy,
    observation: QueueObservation,
    *,
    now: datetime | None = None,
) -> WorkItem:
    evaluation, reasons = evaluate_snapshot(snapshot, policy)
    state = work_state_for_evaluation(evaluation)
    created = now or utcnow()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    score = score_work_item(
        target,
        snapshot,
        evaluation,
        state,
        now=created,
    )
    return WorkItem(
        target=target,
        snapshot=snapshot,
        evaluation=evaluation,
        state=state,
        score=score,
        reasons=reasons,
        observed_queue_depth=observation.queued_actions,
        observed_rate_remaining=observation.rate_remaining,
        created_at=created.astimezone(timezone.utc).isoformat(),
        updated_at=created.astimezone(timezone.utc).isoformat(),
    )


def defer_item(
    item: WorkItem,
    reasons: Sequence[str],
    *,
    now: datetime | None = None,
) -> WorkItem:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return replace(
        item,
        state=WorkState.DEFERRED,
        score=_STATE_SCORE[WorkState.DEFERRED],
        reasons=tuple(dict.fromkeys((*item.reasons, *reasons))),
        updated_at=moment.astimezone(timezone.utc).isoformat(),
    )


def _fair_key(item: WorkItem) -> tuple[int, int, int]:
    # Higher score first.  Ties prefer older PR updates and then lower PR
    # numbers for reproducibility.
    age = recency_age_minutes(item.snapshot)
    return (-item.score, -age, item.target.number)


def schedule_items(
    items: Iterable[WorkItem],
    budget: RunBudget,
    policy: RunnerPolicy,
    *,
    now: datetime | None = None,
) -> Schedule:
    ordered = sorted(items, key=_fair_key)
    ready: list[WorkItem] = []
    deferred: list[WorkItem] = []
    target_slots = budget.remaining_targets()

    for index, item in enumerate(ordered):
        if index >= target_slots:
            deferred.append(
                defer_item(item, ("target_budget_exhausted",), now=now)
            )
            continue
        if deadline_reached(budget, now=now):
            deferred.append(
                defer_item(
                    item,
                    (RunnerReason.DEADLINE.value,),
                    now=now,
                )
            )
            continue
        ready.append(item)

    created = now or utcnow()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return Schedule(
        items=tuple(ready),
        deferred=tuple(deferred),
        created_at=created.astimezone(timezone.utc).isoformat(),
    )


def mutation_candidates(
    schedule: Schedule,
    admission: AdmissionDecision,
    policy: RunnerPolicy,
    budget: RunBudget,
    observation: QueueObservation,
    *,
    now: datetime | None = None,
) -> tuple[WorkItem, ...]:
    if not admission.mutation_authorized:
        return ()
    allowed = budget_allows_mutation(
        budget,
        observation,
        policy,
        now=now,
    )
    if not allowed.allowed:
        return ()

    candidates = [
        item
        for item in schedule.items
        if item.state is WorkState.READY
        and item.evaluation.decision is Decision.MERGE
        and item.evaluation.actions
    ]
    candidates.sort(key=_fair_key)
    return tuple(candidates[: budget.remaining_mutations()])


def schedule_diagnostics(
    schedule: Schedule,
) -> Mapping[str, object]:
    by_state: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for item in schedule.all():
        by_state[item.state.value] = by_state.get(item.state.value, 0) + 1
        band = item.target.priority.value
        by_priority[band] = by_priority.get(band, 0) + 1
    return {
        "scheduled": len(schedule.items),
        "deferred": len(schedule.deferred),
        "by_state": dict(sorted(by_state.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "top": [
            {
                "pr": item.target.number,
                "score": item.score,
                "state": item.state.value,
                "decision": item.evaluation.decision.value,
            }
            for item in schedule.items[:20]
        ],
    }


def observe_queue(
    *,
    queued_actions: int | None,
    rate_remaining: int | None,
    now: datetime | None = None,
) -> QueueObservation:
    moment = now or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return QueueObservation(
        queued_actions=queued_actions,
        rate_remaining=rate_remaining,
        captured_at=moment.astimezone(timezone.utc).isoformat(),
    )


__all__ = [
    "BudgetDecision",
    "MutableBudget",
    "QueueObservation",
    "Schedule",
    "budget_allows_mutation",
    "budget_allows_target",
    "build_work_item",
    "deadline_reached",
    "deadline_remaining_seconds",
    "defer_item",
    "evaluate_snapshot",
    "make_budget",
    "mutation_candidates",
    "observe_queue",
    "recency_age_minutes",
    "schedule_diagnostics",
    "schedule_items",
    "score_work_item",
    "work_state_for_evaluation",
]
