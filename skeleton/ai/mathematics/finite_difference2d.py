"""Two-dimensional finite-difference vector-calculus references."""
from __future__ import annotations

from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, positive_scalar


def _grid(values: Sequence[Sequence[Real]], name: str) -> Matrix:
    grid = finite_matrix(name, values)
    if len(grid) < 3 or len(grid[0]) < 3:
        raise MathInvariantError(
            "2-D finite differences require at least a 3x3 grid",
            reason="insufficient_observations",
            field=name,
        )
    return grid


def _first_axis(values: Matrix, spacing: float, *, axis: int) -> Matrix:
    rows = len(values)
    columns = len(values[0])
    output = [[0.0] * columns for _ in range(rows)]
    if axis == 1:
        for row in range(rows):
            output[row][0] = (-3.0 * values[row][0] + 4.0 * values[row][1] - values[row][2]) / (2.0 * spacing)
            output[row][-1] = (3.0 * values[row][-1] - 4.0 * values[row][-2] + values[row][-3]) / (2.0 * spacing)
            for column in range(1, columns - 1):
                output[row][column] = (values[row][column + 1] - values[row][column - 1]) / (2.0 * spacing)
    else:
        for column in range(columns):
            output[0][column] = (-3.0 * values[0][column] + 4.0 * values[1][column] - values[2][column]) / (2.0 * spacing)
            output[-1][column] = (3.0 * values[-1][column] - 4.0 * values[-2][column] + values[-3][column]) / (2.0 * spacing)
            for row in range(1, rows - 1):
                output[row][column] = (values[row + 1][column] - values[row - 1][column]) / (2.0 * spacing)
    return tuple(tuple(row) for row in output)


def gradient_2d(
    values: Sequence[Sequence[Real]],
    *,
    spacing_x: Real = 1.0,
    spacing_y: Real = 1.0,
) -> tuple[Matrix, Matrix]:
    grid = _grid(values, "values")
    dx = positive_scalar("spacing_x", spacing_x)
    dy = positive_scalar("spacing_y", spacing_y)
    return _first_axis(grid, dx, axis=1), _first_axis(grid, dy, axis=0)


def divergence_2d(
    field_x: Sequence[Sequence[Real]],
    field_y: Sequence[Sequence[Real]],
    *,
    spacing_x: Real = 1.0,
    spacing_y: Real = 1.0,
) -> Matrix:
    u = _grid(field_x, "field_x")
    v = _grid(field_y, "field_y")
    if len(u) != len(v) or len(u[0]) != len(v[0]):
        raise MathInvariantError(
            "vector-field components must share grid shape",
            reason="dimension_mismatch",
            field="field",
        )
    dx = positive_scalar("spacing_x", spacing_x)
    dy = positive_scalar("spacing_y", spacing_y)
    du_dx = _first_axis(u, dx, axis=1)
    dv_dy = _first_axis(v, dy, axis=0)
    return tuple(
        tuple(du_dx[row][column] + dv_dy[row][column] for column in range(len(u[0])))
        for row in range(len(u))
    )


def laplacian_2d(
    values: Sequence[Sequence[Real]],
    *,
    spacing_x: Real = 1.0,
    spacing_y: Real = 1.0,
) -> Matrix:
    grid = _grid(values, "values")
    rows = len(grid)
    columns = len(grid[0])
    if rows < 4 or columns < 4:
        raise MathInvariantError(
            "second-order boundary Laplacian requires at least a 4x4 grid",
            reason="insufficient_observations",
            field="values",
        )
    dx = positive_scalar("spacing_x", spacing_x)
    dy = positive_scalar("spacing_y", spacing_y)
    dx2 = dx * dx
    dy2 = dy * dy
    output = [[0.0] * columns for _ in range(rows)]

    for row in range(rows):
        for column in range(columns):
            if column == 0:
                dxx = (2.0 * grid[row][0] - 5.0 * grid[row][1] + 4.0 * grid[row][2] - grid[row][3]) / dx2
            elif column == columns - 1:
                dxx = (2.0 * grid[row][-1] - 5.0 * grid[row][-2] + 4.0 * grid[row][-3] - grid[row][-4]) / dx2
            else:
                dxx = (grid[row][column - 1] - 2.0 * grid[row][column] + grid[row][column + 1]) / dx2

            if row == 0:
                dyy = (2.0 * grid[0][column] - 5.0 * grid[1][column] + 4.0 * grid[2][column] - grid[3][column]) / dy2
            elif row == rows - 1:
                dyy = (2.0 * grid[-1][column] - 5.0 * grid[-2][column] + 4.0 * grid[-3][column] - grid[-4][column]) / dy2
            else:
                dyy = (grid[row - 1][column] - 2.0 * grid[row][column] + grid[row + 1][column]) / dy2
            output[row][column] = dxx + dyy
    return tuple(tuple(row) for row in output)


def curl_z_2d(
    field_x: Sequence[Sequence[Real]],
    field_y: Sequence[Sequence[Real]],
    *,
    spacing_x: Real = 1.0,
    spacing_y: Real = 1.0,
) -> Matrix:
    u = _grid(field_x, "field_x")
    v = _grid(field_y, "field_y")
    if len(u) != len(v) or len(u[0]) != len(v[0]):
        raise MathInvariantError(
            "vector-field components must share grid shape",
            reason="dimension_mismatch",
            field="field",
        )
    dx = positive_scalar("spacing_x", spacing_x)
    dy = positive_scalar("spacing_y", spacing_y)
    dv_dx = _first_axis(v, dx, axis=1)
    du_dy = _first_axis(u, dy, axis=0)
    return tuple(
        tuple(dv_dx[row][column] - du_dy[row][column] for column in range(len(u[0])))
        for row in range(len(u))
    )
