"""B045 large-world streaming: budgeted, deterministic cell residency planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

CellId = tuple[int, int]


class StreamingError(ValueError):
    pass


@dataclass(frozen=True)
class StreamBudget:
    memory_bytes: int
    max_loads_per_tick: int
    radius: int

    def __post_init__(self) -> None:
        if self.memory_bytes <= 0 or self.max_loads_per_tick <= 0 or self.radius < 0:
            raise StreamingError("invalid budget")


@dataclass(frozen=True)
class StreamPlan:
    load: tuple[CellId, ...]
    unload: tuple[CellId, ...]
    deferred: tuple[CellId, ...]
    resident_bytes: int


def plan_tick(focus: CellId, resident: Iterable[CellId], sizes: Mapping[CellId, int],
              budget: StreamBudget) -> StreamPlan:
    """Load nearest-first within radius under memory and per-tick load budgets."""
    fx, fy = focus
    dist = lambda c: max(abs(c[0] - fx), abs(c[1] - fy))  # noqa: E731
    wanted = sorted((c for c in sizes if dist(c) <= budget.radius), key=lambda c: (dist(c), c))
    res = set(resident)
    unload = sorted(c for c in res if c not in set(wanted))
    keep = [c for c in wanted if c in res]
    used = sum(sizes.get(c, 0) for c in keep)
    load, deferred = [], []
    for c in wanted:
        if c in res:
            continue
        if len(load) < budget.max_loads_per_tick and used + sizes[c] <= budget.memory_bytes:
            load.append(c)
            used += sizes[c]
        else:
            deferred.append(c)
    return StreamPlan(tuple(load), tuple(unload), tuple(deferred), used)
