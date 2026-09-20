"""Fairness-aware scheduler for continuous machine repository stewardship."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .checkpoint import StewardCheckpoint
from .leases import LeaseRegistry
from .model import RepositoryModel
from .work_queue import MachineWorkQueue, QueueItem


_URGENT_LANES = {"repair", "security", "integration", "repository-health"}
_LONG_HORIZON_LANES = {"architecture", "organization", "documentation", "regression"}


@dataclass(frozen=True, slots=True)
class ScheduledObjective:
    item: QueueItem
    effective_priority: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        payload = self.item.as_dict()
        payload["effective_priority"] = self.effective_priority
        payload["schedule_reasons"] = list(self.reasons)
        return payload


def _fairness_bonus(
    item: QueueItem,
    checkpoint: StewardCheckpoint,
    *,
    max_lane_streak: int,
) -> tuple[int, tuple[str, ...]]:
    bonus = 0
    reasons: list[str] = []
    if checkpoint.lane_streak == item.lane and checkpoint.lane_streak_count >= max_lane_streak:
        bonus -= 40
        reasons.append("same-lane streak penalty")
    recent = checkpoint.recent_lane_count(item.lane, window=20)
    if recent == 0:
        bonus += 25
        reasons.append("lane starvation prevention")
    elif recent <= 2:
        bonus += 10
        reasons.append("underrepresented lane")
    if item.lane in _URGENT_LANES:
        bonus += 20
        reasons.append("urgent lane")
    elif item.lane in _LONG_HORIZON_LANES:
        bonus += 5
        reasons.append("long-horizon maintenance lane")
    if item.attempts >= 3:
        bonus -= min(30, item.attempts * 5)
        reasons.append("repeated-attempt penalty")
    return bonus, tuple(reasons)


def schedule_objectives(
    model: RepositoryModel,
    queue: MachineWorkQueue,
    checkpoint: StewardCheckpoint,
    leases: LeaseRegistry,
    *,
    now: int,
    max_objectives: int = 3,
    max_lane_streak: int = 5,
    extra_conflicts: Iterable[str] = (),
) -> tuple[ScheduledObjective, ...]:
    if isinstance(max_objectives, bool) or not isinstance(max_objectives, int) or not 1 <= max_objectives <= 16:
        raise ValueError("max_objectives must be in [1,16]")
    conflicts = set(leases.active_conflicts(now))
    conflicts.update(extra_conflicts)

    candidates = [
        item
        for item in queue.items.values()
        if item.status == "ready"
        and item.repository_fingerprint == model.fingerprint
    ]
    scored: list[ScheduledObjective] = []
    for item in candidates:
        bonus, reasons = _fairness_bonus(
            item,
            checkpoint,
            max_lane_streak=max_lane_streak,
        )
        score = item.priority + bonus
        if checkpoint.fingerprint_stale(model.fingerprint):
            score += 5
            reasons = (*reasons, "repository changed since last completed objective")
        scored.append(ScheduledObjective(item, score, reasons))

    scored.sort(
        key=lambda item: (
            -item.effective_priority,
            item.item.zone,
            item.item.identity,
        )
    )
    selected: list[ScheduledObjective] = []
    for candidate in scored:
        if conflicts.intersection(candidate.item.conflict_keys):
            continue
        selected.append(candidate)
        conflicts.update(candidate.item.conflict_keys)
        if len(selected) >= max_objectives:
            break
    return tuple(selected)


def lane_distribution(checkpoint: StewardCheckpoint) -> dict[str, float]:
    total = sum(checkpoint.lane_counts.values())
    if total <= 0:
        return {}
    return {
        lane: round(count / total, 6)
        for lane, count in sorted(checkpoint.lane_counts.items())
    }
