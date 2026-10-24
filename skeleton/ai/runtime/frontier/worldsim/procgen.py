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


def _distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
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
    return BatchMetrics(n, sum(r.valid for r in results) / n,
                        len({r.digest for r in results}) / n, round(mpd, 6))
