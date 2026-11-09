"""Deterministic minimum-cost bipartite assignment reference."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, finite_scalar
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class AssignmentReport:
    pairs: tuple[tuple[int, int], ...]
    total_cost: float
    row_count: int
    column_count: int
    complete_smaller_partition: bool


def _hungarian_rows_le_columns(cost: Matrix) -> tuple[tuple[int, int], ...]:
    n = len(cost)
    m = len(cost[0])
    # Classic shortest augmenting-path Hungarian method, deterministic by
    # left-to-right column tie-breaking.
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minv[j]:
                    minv[j] = current
                    way[j] = j0
                if minv[j] < delta or (minv[j] == delta and j < j1):
                    delta = minv[j]
                    j1 = j
            if not delta < float("inf"):
                raise MathInvariantError(
                    "assignment augmentation failed",
                    reason="assignment_failure",
                    field="cost",
                )
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    pairs = []
    for column in range(1, m + 1):
        if p[column] != 0:
            pairs.append((p[column] - 1, column - 1))
    pairs.sort()
    return tuple(pairs)


def minimum_cost_assignment(
    costs: Sequence[Sequence[Real]],
) -> AssignmentReport:
    matrix = finite_matrix("costs", costs)
    rows = len(matrix)
    columns = len(matrix[0])

    if rows <= columns:
        pairs = _hungarian_rows_le_columns(matrix)
    else:
        transposed = tuple(
            tuple(matrix[row][column] for row in range(rows))
            for column in range(columns)
        )
        transposed_pairs = _hungarian_rows_le_columns(transposed)
        pairs = tuple(sorted((column, row) for row, column in transposed_pairs))

    expected_pairs = min(rows, columns)
    if len(pairs) != expected_pairs:
        raise MathInvariantError(
            "assignment did not cover the smaller partition",
            reason="assignment_failure",
            field="costs",
        )
    if len({row for row, _ in pairs}) != len(pairs) or len({column for _, column in pairs}) != len(pairs):
        raise MathInvariantError(
            "assignment contains duplicate row or column",
            reason="assignment_failure",
            field="pairs",
        )
    total = compensated_sum(matrix[row][column] for row, column in pairs)
    return AssignmentReport(
        pairs=pairs,
        total_cost=finite_scalar("total_cost", total),
        row_count=rows,
        column_count=columns,
        complete_smaller_partition=True,
    )
