"""Pack independent work into bounded parallel execution waves."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .budgets import derive_zone_budgets
from .model import RepositoryModel
from .scheduler import ScheduledObjective


@dataclass(frozen=True, slots=True)
class WorkWave:
    index: int
    objectives: tuple[ScheduledObjective, ...]
    conflict_keys: tuple[str, ...]
    zones: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "objectives": [item.as_dict() for item in self.objectives],
            "conflict_keys": list(self.conflict_keys),
            "zones": list(self.zones),
        }


def build_parallel_waves(
    model: RepositoryModel,
    objectives: Iterable[ScheduledObjective],
    *,
    max_wave_width: int = 4,
) -> tuple[WorkWave, ...]:
    if isinstance(max_wave_width, bool) or not isinstance(max_wave_width, int) or not 1 <= max_wave_width <= 16:
        raise ValueError("max_wave_width must be in [1,16]")
    budgets = {item.zone: item for item in derive_zone_budgets(model)}
    ordered = sorted(
        tuple(objectives),
        key=lambda item: (
            -item.effective_priority,
            item.item.zone,
            item.item.identity,
        ),
    )
    waves: list[list[ScheduledObjective]] = []
    wave_conflicts: list[set[str]] = []
    wave_zone_counts: list[dict[str, int]] = []

    for objective in ordered:
        placed = False
        item_conflicts = set(objective.item.conflict_keys)
        budget = budgets.get(objective.item.zone)
        zone_limit = budget.max_parallel_objectives if budget else 1
        for index, wave in enumerate(waves):
            if len(wave) >= max_wave_width:
                continue
            if wave_conflicts[index].intersection(item_conflicts):
                continue
            if wave_zone_counts[index].get(objective.item.zone, 0) >= zone_limit:
                continue
            wave.append(objective)
            wave_conflicts[index].update(item_conflicts)
            wave_zone_counts[index][objective.item.zone] = (
                wave_zone_counts[index].get(objective.item.zone, 0) + 1
            )
            placed = True
            break
        if placed:
            continue
        waves.append([objective])
        wave_conflicts.append(set(item_conflicts))
        wave_zone_counts.append({objective.item.zone: 1})

    result: list[WorkWave] = []
    for index, wave in enumerate(waves, start=1):
        result.append(WorkWave(
            index=index,
            objectives=tuple(wave),
            conflict_keys=tuple(sorted(wave_conflicts[index - 1])),
            zones=tuple(sorted(wave_zone_counts[index - 1])),
        ))
    return tuple(result)


def maximum_safe_parallelism(
    model: RepositoryModel,
    objectives: Iterable[ScheduledObjective],
) -> int:
    waves = build_parallel_waves(model, objectives, max_wave_width=16)
    return max((len(wave.objectives) for wave in waves), default=0)
