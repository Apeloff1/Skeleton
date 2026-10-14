"""Regular-grid multilinear interpolation reference primitives."""
from __future__ import annotations

import bisect
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector


def _axis(name: str, values: Sequence[Real]) -> tuple[float, ...]:
    axis = finite_vector(name, values)
    if len(axis) < 2:
        raise MathInvariantError(
            "interpolation axis requires at least two coordinates",
            reason="insufficient_observations",
            field=name,
        )
    for index in range(1, len(axis)):
        if axis[index] <= axis[index - 1]:
            raise MathInvariantError(
                "interpolation axes must be strictly increasing",
                reason="non_monotonic_nodes",
                field=f"{name}[{index}]",
            )
    return axis


def _locate(axis: tuple[float, ...], value: float, name: str) -> tuple[int, float]:
    if value < axis[0] or value > axis[-1]:
        raise MathInvariantError(
            "interpolation point lies outside grid domain",
            reason="extrapolation_forbidden",
            field=name,
        )
    if value == axis[-1]:
        index = len(axis) - 2
        return index, 1.0
    index = bisect.bisect_right(axis, value) - 1
    fraction = (value - axis[index]) / (axis[index + 1] - axis[index])
    return index, fraction


def bilinear_interpolate(
    x_axis: Sequence[Real],
    y_axis: Sequence[Real],
    values: Sequence[Sequence[Real]],
    x: Real,
    y: Real,
) -> float:
    xs = _axis("x_axis", x_axis)
    ys = _axis("y_axis", y_axis)
    rows = tuple(finite_vector(f"values[{index}]", row) for index, row in enumerate(values))
    if len(rows) != len(xs) or any(len(row) != len(ys) for row in rows):
        raise MathInvariantError(
            "bilinear value grid must have shape (len(x_axis), len(y_axis))",
            reason="dimension_mismatch",
            field="values",
        )
    px = finite_scalar("x", x)
    py = finite_scalar("y", y)
    i, tx = _locate(xs, px, "x")
    j, ty = _locate(ys, py, "y")
    v00 = rows[i][j]
    v10 = rows[i + 1][j]
    v01 = rows[i][j + 1]
    v11 = rows[i + 1][j + 1]
    return (
        (1.0 - tx) * (1.0 - ty) * v00
        + tx * (1.0 - ty) * v10
        + (1.0 - tx) * ty * v01
        + tx * ty * v11
    )


def trilinear_interpolate(
    x_axis: Sequence[Real],
    y_axis: Sequence[Real],
    z_axis: Sequence[Real],
    values: Sequence[Sequence[Sequence[Real]]],
    x: Real,
    y: Real,
    z: Real,
) -> float:
    xs = _axis("x_axis", x_axis)
    ys = _axis("y_axis", y_axis)
    zs = _axis("z_axis", z_axis)
    if len(values) != len(xs):
        raise MathInvariantError(
            "trilinear grid x dimension mismatch",
            reason="dimension_mismatch",
            field="values",
        )
    grid: list[tuple[tuple[float, ...], ...]] = []
    for i, slab in enumerate(values):
        if len(slab) != len(ys):
            raise MathInvariantError(
                "trilinear grid y dimension mismatch",
                reason="dimension_mismatch",
                field=f"values[{i}]",
            )
        rows = tuple(finite_vector(f"values[{i}][{j}]", row) for j, row in enumerate(slab))
        if any(len(row) != len(zs) for row in rows):
            raise MathInvariantError(
                "trilinear grid z dimension mismatch",
                reason="dimension_mismatch",
                field=f"values[{i}]",
            )
        grid.append(rows)
    px = finite_scalar("x", x)
    py = finite_scalar("y", y)
    pz = finite_scalar("z", z)
    i, tx = _locate(xs, px, "x")
    j, ty = _locate(ys, py, "y")
    k, tz = _locate(zs, pz, "z")

    total = 0.0
    for dx in (0, 1):
        wx = tx if dx else 1.0 - tx
        for dy in (0, 1):
            wy = ty if dy else 1.0 - ty
            for dz in (0, 1):
                wz = tz if dz else 1.0 - tz
                total += wx * wy * wz * grid[i + dx][j + dy][k + dz]
    return finite_scalar("interpolated_value", total)


def bilinear_gradient(
    x_axis: Sequence[Real],
    y_axis: Sequence[Real],
    values: Sequence[Sequence[Real]],
    x: Real,
    y: Real,
) -> tuple[float, float]:
    xs = _axis("x_axis", x_axis)
    ys = _axis("y_axis", y_axis)
    rows = tuple(finite_vector(f"values[{index}]", row) for index, row in enumerate(values))
    if len(rows) != len(xs) or any(len(row) != len(ys) for row in rows):
        raise MathInvariantError(
            "bilinear value grid shape mismatch",
            reason="dimension_mismatch",
            field="values",
        )
    px = finite_scalar("x", x)
    py = finite_scalar("y", y)
    i, tx = _locate(xs, px, "x")
    j, ty = _locate(ys, py, "y")
    dx = xs[i + 1] - xs[i]
    dy = ys[j + 1] - ys[j]
    v00 = rows[i][j]
    v10 = rows[i + 1][j]
    v01 = rows[i][j + 1]
    v11 = rows[i + 1][j + 1]
    derivative_x = ((1.0 - ty) * (v10 - v00) + ty * (v11 - v01)) / dx
    derivative_y = ((1.0 - tx) * (v01 - v00) + tx * (v11 - v10)) / dy
    return derivative_x, derivative_y
