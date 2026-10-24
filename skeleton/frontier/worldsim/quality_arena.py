"""B050 world generation quality arena: score worlds on reachability, variety,
performance and gameplay constraints, then rank candidates deterministically."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .navigation import NavGrid, reachability_report

WEIGHTS = {"reachability": 0.35, "variety": 0.25, "performance": 0.2, "constraints": 0.2}


@dataclass(frozen=True)
class WorldCandidate:
    world_id: str
    grid: NavGrid
    spawn: tuple[int, int]
    objectives: tuple[tuple[int, int], ...]
    tile_kinds: tuple[str, ...]
    cost_ms: float


@dataclass(frozen=True)
class ArenaScore:
    world_id: str
    total: float
    parts: Mapping[str, float]
    passed: bool
    failures: tuple[str, ...]


def score(c: WorldCandidate, budget_ms: float,
          constraints: Mapping[str, Callable[[WorldCandidate], bool]] | None = None) -> ArenaScore:
    rep = reachability_report(c.grid, c.spawn, c.objectives)
    reach = 1.0 - (len(rep["unreachable"]) / len(c.objectives) if c.objectives else 0.0)
    variety = len(set(c.tile_kinds)) / len(c.tile_kinds) if c.tile_kinds else 0.0
    perf = 1.0 if c.cost_ms <= budget_ms else max(0.0, budget_ms / c.cost_ms)
    failed = tuple(sorted(n for n, f in (constraints or {}).items() if not f(c)))
    cons = 1.0 - (len(failed) / len(constraints) if constraints else 0.0)
    parts = {"reachability": round(reach, 6), "variety": round(variety, 6),
             "performance": round(perf, 6), "constraints": round(cons, 6)}
    fails = failed + (("unreachable_objectives",) if not rep["ok"] else ()) + (("over_budget",) if perf < 1 else ())
    return ArenaScore(c.world_id, round(sum(WEIGHTS[k] * v for k, v in parts.items()), 6), parts, not fails, fails)


def rank(cands: Sequence[WorldCandidate], budget_ms: float, constraints: Any = None) -> list[ArenaScore]:
    return sorted((score(c, budget_ms, constraints) for c in cands), key=lambda s: (-s.passed, -s.total, s.world_id))
