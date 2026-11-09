"""Sequence alignment and trajectory-distance reference metrics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence, TypeVar

from .contracts import MathInvariantError, finite_scalar, finite_vector


T = TypeVar("T")


def levenshtein_distance(
    left: Sequence[T],
    right: Sequence[T],
) -> int:
    if isinstance(left, (str, bytes)):
        a = tuple(left)
    else:
        a = tuple(left)
    if isinstance(right, (str, bytes)):
        b = tuple(right)
    else:
        b = tuple(right)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, left_value in enumerate(a, start=1):
        current = [i]
        for j, right_value in enumerate(b, start=1):
            substitution = previous[j - 1] + (left_value != right_value)
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def normalized_levenshtein_distance(
    left: Sequence[T],
    right: Sequence[T],
) -> float:
    a = tuple(left)
    b = tuple(right)
    length = max(len(a), len(b))
    if length == 0:
        return 0.0
    return levenshtein_distance(a, b) / length


@dataclass(frozen=True, slots=True)
class DTWReport:
    distance: float
    path: tuple[tuple[int, int], ...]
    path_length: int
    normalized_distance: float


def dynamic_time_warping(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    window: int | None = None,
) -> DTWReport:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    n = len(a)
    m = len(b)
    if window is None:
        radius = max(n, m)
    else:
        if isinstance(window, bool) or not isinstance(window, int) or window < 0:
            raise MathInvariantError(
                "DTW window must be a non-negative integer or None",
                reason="invalid_window",
                field="window",
            )
        radius = max(window, abs(n - m))

    infinity = math.inf
    cost = [[infinity] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    predecessor: dict[tuple[int, int], tuple[int, int]] = {}

    for i in range(1, n + 1):
        start = max(1, i - radius)
        end = min(m, i + radius)
        for j in range(start, end + 1):
            local = abs(a[i - 1] - b[j - 1])
            candidates = (
                (cost[i - 1][j - 1], (i - 1, j - 1)),
                (cost[i - 1][j], (i - 1, j)),
                (cost[i][j - 1], (i, j - 1)),
            )
            best_cost, best_predecessor = min(
                candidates,
                key=lambda item: (item[0], item[1][0], item[1][1]),
            )
            if math.isfinite(best_cost):
                cost[i][j] = local + best_cost
                predecessor[(i, j)] = best_predecessor

    if not math.isfinite(cost[n][m]):
        raise MathInvariantError(
            "DTW window does not admit a complete alignment",
            reason="no_alignment_path",
            field="window",
        )

    path: list[tuple[int, int]] = []
    cursor = (n, m)
    while cursor != (0, 0):
        i, j = cursor
        if i == 0 or j == 0 or cursor not in predecessor:
            raise MathInvariantError(
                "DTW predecessor chain is incomplete",
                reason="numerical_invariant_failure",
                field="path",
            )
        path.append((i - 1, j - 1))
        cursor = predecessor[cursor]
    path.reverse()
    distance = finite_scalar("dtw_distance", cost[n][m])
    return DTWReport(
        distance=distance,
        path=tuple(path),
        path_length=len(path),
        normalized_distance=distance / len(path),
    )


def discrete_frechet_distance(
    left: Sequence[Sequence[Real]],
    right: Sequence[Sequence[Real]],
) -> float:
    if not left or not right:
        raise MathInvariantError(
            "Fréchet trajectories must be non-empty",
            reason="empty_trajectory",
            field="trajectory",
        )
    a = tuple(finite_vector(f"left[{i}]", point) for i, point in enumerate(left))
    b = tuple(finite_vector(f"right[{i}]", point) for i, point in enumerate(right))
    dimension = len(a[0])
    if any(len(point) != dimension for point in a + b):
        raise MathInvariantError(
            "Fréchet trajectory points must share a dimension",
            reason="dimension_mismatch",
            field="trajectory",
        )

    cache = [[0.0] * len(b) for _ in range(len(a))]
    for i in range(len(a)):
        for j in range(len(b)):
            distance = math.dist(a[i], b[j])
            if i == 0 and j == 0:
                cache[i][j] = distance
            elif i == 0:
                cache[i][j] = max(cache[i][j - 1], distance)
            elif j == 0:
                cache[i][j] = max(cache[i - 1][j], distance)
            else:
                cache[i][j] = max(
                    min(cache[i - 1][j], cache[i - 1][j - 1], cache[i][j - 1]),
                    distance,
                )
    return finite_scalar("frechet_distance", cache[-1][-1])
