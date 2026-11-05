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
              budget: StreamBudget, heading: tuple[float, float] | None = None,
              path: Iterable[CellId] = (), ahead_bias: float = 1.5,
              behind_radius: int | None = None, path_lookahead: int = 2) -> StreamPlan:
    """Load within radius under memory and per-tick load budgets.

    With ``heading`` (or a nav ``path``), cells ahead of the player and on the
    path load first (see ``plan_tick_directed``). Without them: nearest-first.
    """
    path = tuple(path)
    if heading is not None or path:
        return plan_tick_directed(focus, heading or (0.0, 0.0), resident, sizes, budget,
                                  ahead_bias=ahead_bias, path=path, behind_radius=behind_radius,
                                  path_lookahead=path_lookahead)
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


# --- Heading-aware prioritisation (Wally LD review on #4268, note 7) ---
# Nearest-first ignores travel direction; at speed this pops in ahead of the
# player. Bias priority toward cells along the heading and any nav path.

def _priority(c: CellId, focus: CellId, heading: tuple[float, float],
              ahead_bias: float, path_rank: Mapping[CellId, int]) -> tuple[float, CellId]:
    dx, dy = c[0] - focus[0], c[1] - focus[1]
    cheb = max(abs(dx), abs(dy))
    hx, hy = heading
    norm = (hx * hx + hy * hy) ** 0.5
    if cheb == 0 or norm == 0:
        align = 0.0
    else:
        align = (dx * hx + dy * hy) / (norm * (dx * dx + dy * dy) ** 0.5)  # cosine in [-1, 1]
    p = cheb - ahead_bias * align
    if c in path_rank:
        p = min(p, path_rank[c] * 0.5) - ahead_bias  # cells on the upcoming nav path go first
    if cheb == 0:
        p = float("-inf")  # the cell the player stands in always loads first
    return (round(p, 9), c)


def plan_tick_directed(focus: CellId, heading: tuple[float, float], resident: Iterable[CellId],
                       sizes: Mapping[CellId, int], budget: StreamBudget,
                       ahead_bias: float = 1.5, path: Iterable[CellId] = (),
                       behind_radius: int | None = None, path_lookahead: int = 2) -> StreamPlan:
    """Like ``plan_tick`` but loads cells ahead of the player (and on ``path``) first.

    ``behind_radius`` optionally shrinks the wanted radius for cells behind the
    heading (cosine < 0), freeing memory for look-ahead. Zero heading falls back
    to nearest-first ordering, so stationary players behave like ``plan_tick``.

    Path cells may extend past ``radius`` by at most ``path_lookahead`` cells,
    and any such cell is ordered after every in-radius cell (near before far).
    """
    if ahead_bias < 0:
        raise StreamingError("ahead_bias must be >= 0")
    if path_lookahead < 0:
        raise StreamingError("path_lookahead must be >= 0")
    fx, fy = focus
    hx, hy = heading
    path_rank = {c: i for i, c in enumerate(path) if c in sizes}

    def in_range(c: CellId) -> bool:
        dx, dy = c[0] - fx, c[1] - fy
        d = max(abs(dx), abs(dy))
        if c in path_rank:
            return d <= budget.radius + path_lookahead
        if behind_radius is not None and dx * hx + dy * hy < 0:
            return d <= min(behind_radius, budget.radius)
        return d <= budget.radius

    beyond = lambda c: max(abs(c[0] - fx), abs(c[1] - fy)) > budget.radius  # noqa: E731
    wanted = sorted((c for c in sizes if in_range(c)),
                    key=lambda c: (beyond(c), _priority(c, focus, heading, ahead_bias, path_rank)))
    wanted_set = set(wanted)
    res = set(resident)
    unload = sorted(c for c in res if c not in wanted_set)
    used = sum(sizes.get(c, 0) for c in wanted if c in res)
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
