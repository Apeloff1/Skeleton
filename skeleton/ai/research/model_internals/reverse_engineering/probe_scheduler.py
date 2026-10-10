"""Budget-aware deterministic scheduling of characterization probes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ProbeTask:
    probe_id: str
    domain: str
    estimated_cost: float
    information_value: float
    risk: float = 0.0
    prerequisite_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.probe_id or not self.domain:
            raise ReverseEngineeringError("probe task identity is required")
        for value, name in (
            (self.estimated_cost, "estimated_cost"),
            (self.information_value, "information_value"),
            (self.risk, "risk"),
        ):
            if not isfinite(value) or value < 0.0:
                raise ReverseEngineeringError(f"{name} must be finite and non-negative")
        if self.estimated_cost == 0.0:
            raise ReverseEngineeringError("estimated_cost must be positive")
        if len(self.prerequisite_ids) != len(set(self.prerequisite_ids)):
            raise ReverseEngineeringError("probe prerequisites must be unique")
        if self.probe_id in self.prerequisite_ids:
            raise ReverseEngineeringError("probe cannot depend on itself")

    @property
    def priority(self) -> float:
        return self.information_value / self.estimated_cost / (1.0 + self.risk)


@dataclass(frozen=True)
class ProbeSchedule:
    budget: float
    spent: float
    selected_ids: tuple[str, ...]
    skipped_ids: tuple[str, ...]
    selected_domains: tuple[str, ...]
    total_information_value: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "spent": self.spent,
            "selected_ids": list(self.selected_ids),
            "skipped_ids": list(self.skipped_ids),
            "selected_domains": list(self.selected_domains),
            "total_information_value": self.total_information_value,
            "digest": self.digest,
        }


def schedule_probes(
    tasks: Sequence[ProbeTask],
    *,
    budget: float,
) -> ProbeSchedule:
    if not tasks:
        raise ReverseEngineeringError("probe scheduling requires tasks")
    if not isfinite(budget) or budget <= 0.0:
        raise ReverseEngineeringError("budget must be finite and positive")
    ids = [task.probe_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("probe task ids must be unique")
    known = set(ids)
    for task in tasks:
        missing = set(task.prerequisite_ids) - known
        if missing:
            raise ReverseEngineeringError(
                f"probe {task.probe_id!r} has unknown prerequisites"
            )

    ordered = sorted(tasks, key=lambda task: (-task.priority, task.probe_id))
    selected: list[ProbeTask] = []
    selected_ids: set[str] = set()
    spent = 0.0
    pending = list(ordered)
    progress = True
    while progress and pending:
        progress = False
        next_pending: list[ProbeTask] = []
        for task in pending:
            if not set(task.prerequisite_ids).issubset(selected_ids):
                next_pending.append(task)
                continue
            if spent + task.estimated_cost <= budget + 1e-12:
                selected.append(task)
                selected_ids.add(task.probe_id)
                spent += task.estimated_cost
                progress = True
            else:
                next_pending.append(task)
        pending = next_pending

    skipped = tuple(sorted(task.probe_id for task in tasks if task.probe_id not in selected_ids))
    selected_tuple = tuple(task.probe_id for task in selected)
    payload = {
        "budget": budget,
        "tasks": [
            {
                "probe_id": task.probe_id,
                "domain": task.domain,
                "estimated_cost": task.estimated_cost,
                "information_value": task.information_value,
                "risk": task.risk,
                "prerequisite_ids": list(task.prerequisite_ids),
            }
            for task in sorted(tasks, key=lambda value: value.probe_id)
        ],
        "selected_ids": list(selected_tuple),
    }
    return ProbeSchedule(
        budget=budget,
        spent=spent,
        selected_ids=selected_tuple,
        skipped_ids=skipped,
        selected_domains=tuple(sorted({task.domain for task in selected})),
        total_information_value=sum(task.information_value for task in selected),
        digest=stable_digest(payload),
    )
