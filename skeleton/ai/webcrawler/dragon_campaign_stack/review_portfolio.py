"""Finite human review allocation with explicit measured/estimated effort.

An agenda can include hundreds of pending tasks and dependencies. This
planner proposes a bounded review *portfolio* with fair coverage across
objectives while respecting a declared human time budget. It never initiates
a worker, approves content, generates reviewer identities or persists work.

Operator-provided effort estimates are assumptions, never observed SLOs.
Unknown estimates fail closed unless an explicit, bounded default is chosen.
Review work cannot silently consume a task with unmet prerequisites.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import CampaignMandate, digest, finite, integer
from .review_agenda import ReviewAgenda, ReviewTask
from .review_replay import ReviewReplay


@dataclass(frozen=True)
class ReviewEffort:
    task_type: str
    estimated_minutes: int
    estimate_basis: str

    def __post_init__(self):
        if self.task_type not in {
            "source_policy", "passage_integrity", "source_provenance",
            "claim_contradiction", "claim_corroboration", "objective_gap",
            "human_fact_review",
        }:
            raise ValueError("unknown review effort class")
        integer(self.estimated_minutes, "review effort minutes", 1, 180)
        if self.estimate_basis not in ("operator_estimate", "measured_history"):
            raise ValueError("unsupported review effort provenance")


@dataclass(frozen=True)
class PortfolioAssignment:
    task_id: str
    task_type: str
    objective_id: str | None
    source_id: str | None
    priority: float
    assigned_order: int
    estimated_minutes: int
    prerequisites_scheduled: tuple[str, ...]
    estimate_basis: str
    binding: str = "operator_review_proposal_only"


@dataclass(frozen=True)
class ReviewPortfolio:
    mandate_digest: str
    source_snapshot_digest: str
    agenda_digest: str
    replay_digest: str | None
    time_budget_minutes: int
    consumed_minutes_estimated: int
    remaining_minutes_estimated: int
    tasks_selected: tuple[PortfolioAssignment, ...]
    unscheduled_task_ids: tuple[str, ...]
    unscheduled_reasons: tuple[tuple[str, str], ...]
    objective_coverage: tuple[tuple[str, int], ...]
    portfolio_digest: str
    assignments_persisted: bool = False
    operator_authorized: bool = False
    actual_effort_measured: bool = False


def allocate_human_review(
    mandate: CampaignMandate,
    agenda: ReviewAgenda,
    effort: Iterable[ReviewEffort],
    *,
    now: float,
    authorized: bool,
    replay: ReviewReplay | None = None,
    budget_minutes: int = 240,
    max_assignments: int = 32,
    max_per_objective: int = 12,
    include_dependencies: bool = True,
) -> ReviewPortfolio:
    mandate.admit(now=now, authorized=authorized)
    integer(budget_minutes, "review time budget", 1, 24 * 60)
    integer(max_assignments, "review assignment limit", 1, 128)
    integer(max_per_objective, "review objective fairness cap", 1, 128)
    if type(include_dependencies) is not bool:
        raise ValueError("review dependency policy must be explicit")
    if agenda.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign operator review agenda")
    if replay is not None and (
        replay.mandate_digest != mandate.fingerprint
        or replay.source_snapshot_digest != agenda.source_snapshot_digest
        or replay.agenda_digest != agenda.agenda_digest
        or replay.policy_digest != agenda.policy_digest
    ):
        raise PermissionError("review replay does not match current agenda")
    rows = tuple(effort)
    if not rows or len(rows) > 7:
        raise ValueError("bounded explicit operator effort estimates required")
    by_kind = {}
    for row in rows:
        if not isinstance(row, ReviewEffort):
            raise TypeError("typed review effort assumption required")
        if row.task_type in by_kind:
            raise ValueError("duplicate review effort estimate")
        by_kind[row.task_type] = row
    if set(by_kind) != {row.task_type for row in agenda.tasks}:
        raise ValueError("missing or surplus review effort class")
    tasks = {row.task_id: row for row in agenda.tasks}
    if len(tasks) != len(agenda.tasks):
        raise ValueError("duplicate review task in work allocation")
    states = {row.task_id: row for row in replay.task_states} if replay else {}
    if replay and set(states) != set(tasks):
        raise PermissionError("review replay task universe mismatch")
    done = {
        task_id for task_id, state in states.items()
        if state.operator_reviewed
    }
    forbidden = {
        task_id for task_id, state in states.items()
        if not state.source_policy_current
        or state.state == "rejected"
    }
    if done & forbidden:
        raise PermissionError("reviewed event now contradicts source policy")
    selected = []
    selected_ids = set()
    objective_counts = defaultdict(int)
    remaining = budget_minutes
    reasons = {}
    candidates = sorted(
        (task for task in agenda.tasks if task.task_id not in done),
        key=lambda row: (-row.priority, row.objective_id or "",
                         row.task_type, row.task_id),
    )

    def closure(task_id: str, active: set[str]) -> list[ReviewTask]:
        if task_id in done or task_id in selected_ids:
            return []
        if task_id in forbidden:
            raise PermissionError("withdrawn or rejected task cannot be allocated")
        if task_id in active:
            raise ValueError("cyclic review task allocation")
        active.add(task_id)
        task = tasks[task_id]
        required = []
        for predecessor in task.predecessors:
            if predecessor not in tasks:
                raise ValueError("dangling review dependency")
            if predecessor not in done and predecessor not in selected_ids:
                if not include_dependencies:
                    raise ValueError("review prerequisites not satisfied")
                required.extend(closure(predecessor, active))
        required.append(task)
        active.remove(task_id)
        return required

    for task in candidates:
        if task.task_id in selected_ids:
            continue
        if task.task_id in forbidden:
            reasons[task.task_id] = "source_policy_or_prior_rejection"
            continue
        try:
            requested = closure(task.task_id, set())
        except PermissionError:
            reasons[task.task_id] = "required_source_or_review_rejected"
            continue
        except ValueError:
            reasons[task.task_id] = "unresolved_dependency"
            continue
        batch = []
        batch_ids = set()
        for entry in requested:
            if entry.task_id in done or entry.task_id in selected_ids or entry.task_id in batch_ids:
                continue
            batch.append(entry)
            batch_ids.add(entry.task_id)
        charge = sum(by_kind[x.task_type].estimated_minutes for x in batch)
        if charge > remaining:
            reasons[task.task_id] = "insufficient_explicit_time_budget"
            continue
        if len(selected) + len(batch) > max_assignments:
            reasons[task.task_id] = "review_assignment_capacity"
            continue
        projected_counts = dict(objective_counts)
        for entry in batch:
            if entry.objective_id is not None:
                projected_counts[entry.objective_id] = (
                    projected_counts.get(entry.objective_id, 0) + 1
                )
        if any(n > max_per_objective for n in projected_counts.values()):
            reasons[task.task_id] = "objective_fairness_cap"
            continue
        for entry in batch:
            if entry.task_id in selected_ids:
                continue
            charge_one = by_kind[entry.task_type]
            prerequisites = tuple(
                x for x in entry.predecessors if x in selected_ids
            )
            selected.append(PortfolioAssignment(
                task_id=entry.task_id,
                task_type=entry.task_type,
                objective_id=entry.objective_id,
                source_id=entry.source_id,
                priority=entry.priority,
                assigned_order=len(selected),
                estimated_minutes=charge_one.estimated_minutes,
                prerequisites_scheduled=prerequisites,
                estimate_basis=charge_one.estimate_basis,
            ))
            selected_ids.add(entry.task_id)
            if entry.objective_id is not None:
                objective_counts[entry.objective_id] += 1
            remaining -= charge_one.estimated_minutes
    not_selected = tuple(sorted(
        set(tasks) - selected_ids - done
    ))
    for task_id in not_selected:
        reasons.setdefault(task_id, "not_selected_within_current_review_budget")
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": agenda.source_snapshot_digest,
        "agenda": agenda.agenda_digest,
        "replay": replay.replay_digest if replay else None,
        "effort": [asdict(row) for row in sorted(rows, key=lambda x: x.task_type)],
        "time_budget": budget_minutes, "remaining": remaining,
        "assignments": [asdict(row) for row in selected],
        "unscheduled": sorted(reasons.items()),
        "fairness": sorted(objective_counts.items()),
        "limits": (max_assignments, max_per_objective, include_dependencies),
    }
    return ReviewPortfolio(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=agenda.source_snapshot_digest,
        agenda_digest=agenda.agenda_digest,
        replay_digest=replay.replay_digest if replay else None,
        time_budget_minutes=budget_minutes,
        consumed_minutes_estimated=budget_minutes - remaining,
        remaining_minutes_estimated=remaining,
        tasks_selected=tuple(selected),
        unscheduled_task_ids=not_selected,
        unscheduled_reasons=tuple(sorted(reasons.items())),
        objective_coverage=tuple(sorted(objective_counts.items())),
        portfolio_digest=digest(payload),
    )
