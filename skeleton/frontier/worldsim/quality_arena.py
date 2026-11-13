"""B050 world generation quality arena: score worlds on reachability, variety,
performance and gameplay constraints, then rank candidates deterministically."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .navigation import GateSpec, NavGrid, detect_softlocks, reachability_report

WEIGHTS = {"reachability": 0.35, "variety": 0.25, "performance": 0.2, "constraints": 0.2}


@dataclass(frozen=True)
class WorldCandidate:
    world_id: str
    grid: NavGrid
    spawn: tuple[int, int]
    objectives: tuple[tuple[int, int], ...]
    tile_kinds: tuple[str, ...]
    cost_ms: float
    tile_rows: tuple[tuple[str, ...], ...] | None = None  # 2D tile grid; else tile_kinds reshaped


@dataclass(frozen=True)
class ArenaScore:
    world_id: str
    total: float
    parts: Mapping[str, float]
    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...] = ()  # non-failing notes, e.g. "tile_layout_fallback"


class TileLayoutError(ValueError):
    pass


def score(c: WorldCandidate, budget_ms: float,
          constraints: Mapping[str, Callable[[WorldCandidate], bool]] | None = None,
          strict_tiles: bool = False) -> ArenaScore:
    rep = reachability_report(c.grid, c.spawn, c.objectives)
    reach = 1.0 - (len(rep["unreachable"]) / len(c.objectives) if c.objectives else 0.0)
    tiles, fallback = tile_layout(c, strict=strict_tiles)
    variety = structured_variety(tiles)
    perf = 1.0 if c.cost_ms <= budget_ms else max(0.0, budget_ms / c.cost_ms)
    failed = tuple(sorted(n for n, f in (constraints or {}).items() if not f(c)))
    cons = 1.0 - (len(failed) / len(constraints) if constraints else 0.0)
    parts = {"reachability": round(reach, 6), "variety": round(variety, 6),
             "performance": round(perf, 6), "constraints": round(cons, 6)}
    fails = failed + (("unreachable_objectives",) if not rep["ok"] else ()) + (("over_budget",) if perf < 1 else ())
    return ArenaScore(c.world_id, round(sum(WEIGHTS[k] * v for k, v in parts.items()), 6), parts, not fails, fails,
                      ("tile_layout_fallback",) if fallback else ())


def tile_layout(c: WorldCandidate, strict: bool = False) -> tuple[list[list[str]], bool]:
    """2D tiles for variety plus a fallback flag.

    Explicit ``tile_rows`` win; else ``tile_kinds`` laid out over the nav grid
    when sizes match. On a size mismatch the tiles become a single row and the
    flag is True (variety is then unreliable); with ``strict`` it raises instead.
    """
    if c.tile_rows:
        return [list(r) for r in c.tile_rows], False
    k, w = list(c.tile_kinds), c.grid.width
    if not k:
        return [], False
    if len(k) == w * c.grid.height:
        return [k[i:i + w] for i in range(0, len(k), w)], False
    if strict:
        raise TileLayoutError(f"{c.world_id}: {len(k)} tile_kinds for {w}x{c.grid.height} grid; pass tile_rows")
    return [k], True


def _tile_grid(c: WorldCandidate) -> list[list[str]]:
    return tile_layout(c)[0]


def _gate_failures(c: WorldCandidate, base: ArenaScore, gates: GateSpec | None) -> tuple[str, ...]:
    """Hard reachability gate shared by ``rank`` and ``score_paced``."""
    if not c.objectives:
        return ()
    lock = detect_softlocks(c.grid, gates or GateSpec(), c.spawn, c.objectives)
    return (("softlock",) if lock["softlock_cells"] else ()) + \
        (("unreachable_objectives",) if "unreachable_objectives" not in base.failures
         and not lock.get("goal_reachable", True) else ())


def rank(cands: Sequence[WorldCandidate], budget_ms: float, constraints: Any = None,
         gates: GateSpec | None = None) -> list[ArenaScore]:
    """Rank candidates. Same hard gate as ``score_paced``: a softlocked world or
    one with an unreachable objective scores 0 and fails, so it can't rank high.
    ``gates`` (optional) describes keys/doors; default is an ungated GateSpec."""
    out = []
    for c in cands:
        s = score(c, budget_ms, constraints)
        gf = _gate_failures(c, s, gates)
        if "unreachable_objectives" in s.failures:  # already failing; softlock adds no signal
            gf = tuple(f for f in gf if f != "softlock")
        if gf or "unreachable_objectives" in s.failures:
            s = ArenaScore(s.world_id, 0.0, s.parts, False, s.failures + gf, s.warnings)
        out.append(s)
    return sorted(out, key=lambda s: (-s.passed, -s.total, s.world_id))


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
        if run == max_plateau:  # count each plateau run once, not every flat step
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
                constraints: Mapping[str, Callable[[WorldCandidate], bool]] | None = None,
                gates: GateSpec | None = None) -> ArenaScore:
    """Paced score. Reachability is a hard gate: any unreachable objective or
    softlock (state from which no objective can be reached) scores 0 and fails."""
    base = score(c, budget_ms, constraints)
    gate_fails = _gate_failures(c, base, gates)
    if gate_fails or "unreachable_objectives" in base.failures:
        parts = dict(base.parts, pacing=0.0, encounter_spacing=0.0)
        return ArenaScore(c.world_id, 0.0, parts, False, base.failures + gate_fails, base.warnings)
    parts = dict(base.parts)
    parts["pacing"] = pacing_score(intensity)
    parts["encounter_spacing"] = encounter_spacing_score(encounters, *gap)
    fails = base.failures + (("flat_pacing",) if parts["pacing"] < 0.5 else ()) \
        + (("encounter_spacing",) if parts["encounter_spacing"] < 0.5 else ())
    total = round(sum(PACED_WEIGHTS[k] * v for k, v in parts.items()), 6)
    return ArenaScore(c.world_id, total, parts, not fails, fails, base.warnings)


# --- Structured variety (Wally LD review on #4268, note 4) ---
# unique-kinds / tile-count rewards noise. Readable space = several kinds
# arranged in coherent regions. Score = normalised kind entropy x spatial
# coherence above chance, so salt-and-pepper noise and monotone maps both score low.

def structured_variety(tiles: Sequence[Sequence[str]], ideal_kinds: int = 4) -> float:
    """Variety in [0, 1] for a 2D grid of tile kinds that penalises unstructured randomness."""
    import math
    from collections import Counter

    if not tiles or not tiles[0] or len({len(r) for r in tiles}) != 1:
        return 0.0
    flat = [k for r in tiles for k in r]
    counts = Counter(flat)
    k = len(counts)
    if k < 2:
        return 0.0
    n = len(flat)
    probs = [v / n for v in counts.values()]
    entropy = -sum(p * math.log(p) for p in probs) / math.log(k)
    kinds_term = min(1.0, (k - 1) / max(1, ideal_kinds - 1))
    same = pairs = 0
    h, w = len(tiles), len(tiles[0])
    for y in range(h):
        for x in range(w):
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx < w and ny < h:
                    pairs += 1
                    same += tiles[y][x] == tiles[ny][nx]
    if not pairs:
        return 0.0
    chance = sum(p * p for p in probs)  # expected same-kind adjacency if tiles were shuffled
    coherence = max(0.0, (same / pairs - chance) / (1 - chance)) if chance < 1 else 0.0
    return round(entropy * kinds_term * coherence, 6)


def score_structured(c: WorldCandidate, budget_ms: float, tiles: Sequence[Sequence[str]],
                     constraints: Mapping[str, Callable[[WorldCandidate], bool]] | None = None) -> ArenaScore:
    """``score`` with variety replaced by ``structured_variety`` over the tile grid."""
    base = score(c, budget_ms, constraints)
    parts = dict(base.parts)
    parts["variety"] = structured_variety(tiles)
    return ArenaScore(c.world_id, round(sum(WEIGHTS[k] * v for k, v in parts.items()), 6),
                      parts, base.passed, base.failures)
