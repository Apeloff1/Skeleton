"""Deterministic operator-review capacity planning, never work authorization.

Turns existing policy-bound human-review tasks into bounded hypothetical
reviewer lanes. It does not execute work, assign real employees, sign reviews,
dismiss holds, or promote untrusted source text to accepted knowledge.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest, integer
from .review_triage import ForensicReviewQueue


@dataclass(frozen=True)
class HypotheticalReviewerSlot:
    task_id: str
    reviewer_lane: int
    predicted_minutes: int
    risk: str
    reason: str
    would_require_authenticated_human_action: bool = True
    task_completed: bool = False


@dataclass(frozen=True)
class ReviewCapacityPlan:
    review_queue_digest: str
    lane_count: int
    total_budget_minutes: int
    allocated_minutes: int
    selected_task_ids: tuple[str, ...]
    deferred_task_ids: tuple[str, ...]
    assignments: tuple[HypotheticalReviewerSlot, ...]
    unaddressed_critical_tasks: tuple[str, ...]
    plan_digest: str
    human_reviews_performed: bool = False
    task_completion_asserted: bool = False
    external_workers_started: bool = False


_DEFAULT_MINUTES = {"critical": 40, "high": 25, "medium": 15, "low": 10}


def plan_review_capacity(
    queue: ForensicReviewQueue,
    *, lanes: int = 4, budget_minutes: int = 480,
    max_assignments: int = 128,
) -> ReviewCapacityPlan:
    if not isinstance(queue, ForensicReviewQueue):
        raise TypeError("protected human review queue required")
    integer(lanes, "reviewer lane cap", 1, 16)
    integer(budget_minutes, "reviewer budget minutes", 1, 20_000)
    integer(max_assignments, "review task selection cap", 1, 256)
    if not queue.human_review_required or queue.automatic_publication_permitted:
        raise PermissionError("review planner refuses elevated source policy")
    if len(queue.tasks) > 256 or len({x.task_id for x in queue.tasks}) != len(queue.tasks):
        raise ValueError("invalid bounded review queue")
    for task in queue.tasks:
        if task.risk not in _DEFAULT_MINUTES or task.model_may_decide or (
            task.policy_mutation_authorized
        ):
            raise PermissionError("unreviewable or independently unauthorized task")
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(queue.tasks, key=lambda t: (
        rank[t.risk], t.reason, t.task_id,
    ))
    loads = [0] * lanes
    selected, deferred, assignments = [], [], []
    for task in ordered:
        cost = _DEFAULT_MINUTES[task.risk]
        lane = min(range(lanes), key=lambda i: (loads[i], i))
        if len(assignments) >= max_assignments or sum(loads) + cost > budget_minutes:
            deferred.append(task.task_id)
            continue
        loads[lane] += cost
        selected.append(task.task_id)
        assignments.append(HypotheticalReviewerSlot(
            task.task_id, lane, cost, task.risk, task.reason,
        ))
    unaddressed = tuple(sorted(
        x.task_id for x in ordered
        if x.risk == "critical" and x.task_id not in selected
    ))
    payload = {
        "queue": queue.queue_digest, "lanes": lanes, "budget": budget_minutes,
        "max": max_assignments, "assignments": [asdict(x) for x in assignments],
        "deferred": deferred, "critical": unaddressed,
    }
    return ReviewCapacityPlan(
        queue.queue_digest, lanes, budget_minutes,
        sum(loads), tuple(selected), tuple(deferred), tuple(assignments),
        unaddressed, digest(payload),
    )
