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


# --- Pacing and encounter spacing (Wally review on #4268) ---

def pacing_score(intensity: Sequence[float], max_plateau: int = 3) -> float:
    """1.0 for a rising-with-relief curve; penalise flat plateaus and no climax.

    ``intensity`` is per-segment along the critical path (0..1).
    """
    if len(intensity) < 2:
        return 0.0
    plateaus = run = 0
    for a, b in zip(intensity, intensity[1:]):
        run = run + 1 if abs(a - b) < 1e-9 else 0
        if run >= max_plateau:
            plateaus += 1
    peak_late = intensity.index(max(intensity)) >= len(intensity) // 2
    reliefs = sum(1 for a, b in zip(intensity, intensity[1:]) if b < a)
    score = 0.5 * peak_late + 0.5 * min(1.0, reliefs / max(1, len(intensity) // 4))
    return round(max(0.0, score - 0.1 * plateaus), 6)


def encounter_spacing_score(positions: Sequence[float], min_gap: float, max_gap: float) -> float:
    """Fraction of consecutive encounter gaps within [min_gap, max_gap]."""
    pts = sorted(positions)
    if len(pts) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(pts, pts[1:])]
    return round(sum(min_gap <= g <= max_gap for g in gaps) / len(gaps), 6)


PACED_WEIGHTS = {"reachability": 0.3, "variety": 0.15, "performance": 0.15,
                 "constraints": 0.15, "pacing": 0.15, "encounter_spacing": 0.1}


def score_paced(c: WorldCandidate, budget_ms: float, intensity: Sequence[float],
                encounters: Sequence[float], gap: tuple[float, float] = (2.0, 8.0),
                constraints: Mapping[str, Callable[[WorldCandidate], bool]] | None = None) -> ArenaScore:
    base = score(c, budget_ms, constraints)
    parts = dict(base.parts)
    parts["pacing"] = pacing_score(intensity)
    parts["encounter_spacing"] = encounter_spacing_score(encounters, *gap)
    fails = base.failures + (("flat_pacing",) if parts["pacing"] < 0.5 else ()) \
        + (("encounter_spacing",) if parts["encounter_spacing"] < 0.5 else ())
    total = round(sum(PACED_WEIGHTS[k] * v for k, v in parts.items()), 6)
    return ArenaScore(c.world_id, total, parts, not fails, fails)
