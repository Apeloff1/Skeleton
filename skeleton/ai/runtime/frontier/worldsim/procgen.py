"""B042 procedural generation kernel: seeded, constraint-checked, measured."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ._digest import digest

Generator = Callable[[random.Random, Mapping[str, Any]], Mapping[str, Any]]
Constraint = Callable[[Mapping[str, Any]], bool]


class ProcgenError(ValueError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    seed: int
    artifact: Mapping[str, Any]
    valid: bool
    failed_constraints: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class BatchMetrics:
    count: int
    validity_rate: float
    diversity: float  # unique digests / count
    mean_pairwise_distance: float


def derive_seed(root: int, *labels: object) -> int:
    return int(digest([root, *[str(x) for x in labels]])[:12], 16)


def generate(gen: Generator, seed: int, params: Mapping[str, Any],
             constraints: Mapping[str, Constraint] | None = None) -> GenerationResult:
    if not isinstance(seed, int) or seed < 0:
        raise ProcgenError("seed must be a non-negative int")
    art = dict(gen(random.Random(seed), params))
    failed = tuple(sorted(n for n, c in (constraints or {}).items() if not c(art)))
    return GenerationResult(seed, art, not failed, failed, digest(art))


def _is_layout(art: Mapping[str, Any]) -> bool:
    rows = art.get("rows")
    return isinstance(rows, (list, tuple)) and bool(rows) and all(isinstance(r, str) for r in rows)


def _distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Structural distance for grid layouts (``rows``), key-wise for other artifacts."""
    if _is_layout(a) and _is_layout(b):
        return structural_distance(layout_features(a["rows"]), layout_features(b["rows"]))
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    return sum(1 for k in keys if a.get(k) != b.get(k)) / len(keys)


def generate_batch(gen: Generator, root_seed: int, n: int, params: Mapping[str, Any],
                   constraints: Mapping[str, Constraint] | None = None
                   ) -> tuple[list[GenerationResult], BatchMetrics]:
    if n <= 0:
        raise ProcgenError("n must be positive")
    results = [generate(gen, derive_seed(root_seed, i), params, constraints) for i in range(n)]
    return results, measure(results)


def measure(results: Sequence[GenerationResult]) -> BatchMetrics:
    n = len(results)
    if n == 0:
        return BatchMetrics(0, 0.0, 0.0, 0.0)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    mpd = (sum(_distance(results[i].artifact, results[j].artifact) for i, j in pairs) / len(pairs)) if pairs else 0.0
    if all(_is_layout(r.artifact) for r in results):
        # grids: share of structurally distinct layouts, not unique byte digests
        diversity = measure_structural(results).distinct_layouts
    else:
        diversity = len({r.digest for r in results}) / n
    return BatchMetrics(n, sum(r.valid for r in results) / n, diversity, round(mpd, 6))


# --- Structural layout diversity (Wally LD review on #4268, note 6) ---
# Key-wise equality says two grids differ if any byte differs; level design
# needs "are these meaningfully different spaces". Compare structural features.

FEATURE_KEYS = ("rooms", "open_ratio", "path_length", "branching", "dead_ends", "loops")


def layout_features(rows: Sequence[str], wall: str = "#") -> dict[str, float]:
    """Structural features of a grid layout ('#' = wall, anything else open).

    rooms: 4-connected open components; path_length: BFS diameter estimate of
    the largest component (normalised by open cells); branching / dead_ends:
    share of open cells with >=3 / exactly 1 open neighbour; loops: cycle rank
    (edges - nodes + components) normalised by open cells.
    """
    if not rows or len({len(r) for r in rows}) != 1:
        raise ProcgenError("rows must be non-empty and rectangular")
    open_cells = {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != wall}
    total = len(rows) * len(rows[0])
    if not open_cells:
        return {k: 0.0 for k in FEATURE_KEYS}

    def nbrs(c: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = c
        return [n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if n in open_cells]

    def bfs(start: tuple[int, int]) -> dict[tuple[int, int], int]:
        dist, frontier = {start: 0}, [start]
        while frontier:
            nxt = []
            for c in frontier:
                for n in nbrs(c):
                    if n not in dist:
                        dist[n] = dist[c] + 1
                        nxt.append(n)
            frontier = nxt
        return dist

    comps: list[set[tuple[int, int]]] = []
    seen: set[tuple[int, int]] = set()
    for c in sorted(open_cells):
        if c not in seen:
            comp = set(bfs(c))
            seen |= comp
            comps.append(comp)
    largest = max(comps, key=lambda s: (len(s), min(s)))
    far = max(bfs(min(largest)).items(), key=lambda kv: (kv[1], kv[0]))[0]
    diameter = max(bfs(far).values())
    degrees = [len(nbrs(c)) for c in open_cells]
    edges = sum(degrees) // 2
    n = len(open_cells)
    return {
        "rooms": float(len(comps)),
        "open_ratio": round(n / total, 6),
        "path_length": round(diameter / n, 6),
        "branching": round(sum(d >= 3 for d in degrees) / n, 6),
        "dead_ends": round(sum(d == 1 for d in degrees) / n, 6),
        "loops": round((edges - n + len(comps)) / n, 6),
    }


def structural_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Mean per-feature distance in [0, 1]; room counts compared relatively."""
    ds = []
    for k in FEATURE_KEYS:
        x, y = float(a.get(k, 0.0)), float(b.get(k, 0.0))
        if k == "rooms":
            ds.append(abs(x - y) / max(x, y, 1.0))
        else:
            ds.append(min(1.0, abs(x - y)))
    return round(sum(ds) / len(ds), 6)


@dataclass(frozen=True)
class StructuralMetrics:
    count: int
    mean_structural_distance: float
    min_structural_distance: float
    distinct_layouts: float  # share of results whose nearest neighbour is >= threshold away


def measure_structural(results: Sequence[GenerationResult], key: str = "rows",
                       threshold: float = 0.05) -> StructuralMetrics:
    feats = [layout_features(r.artifact[key]) for r in results]
    n = len(feats)
    if n < 2:
        return StructuralMetrics(n, 0.0, 0.0, float(n))
    d = {(i, j): structural_distance(feats[i], feats[j]) for i in range(n) for j in range(i + 1, n)}
    nearest = [min(d[(min(i, j), max(i, j))] for j in range(n) if j != i) for i in range(n)]
    return StructuralMetrics(n, round(sum(d.values()) / len(d), 6), min(d.values()),
                             round(sum(x >= threshold for x in nearest) / n, 6))
