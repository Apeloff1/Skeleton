"""Linear one-dimensional finite-element assembly and Poisson references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector
from .linear import solve_linear_system


ScalarFunction = Callable[[float], Real]


def _nodes(nodes: Sequence[Real]) -> Vector:
    values = finite_vector("nodes", nodes)
    if len(values) < 2:
        raise MathInvariantError(
            "finite elements require at least two nodes",
            reason="insufficient_observations",
            field="nodes",
        )
    for index in range(1, len(values)):
        if values[index] <= values[index - 1]:
            raise MathInvariantError(
                "finite-element nodes must be strictly increasing",
                reason="non_monotonic_nodes",
                field=f"nodes[{index}]",
            )
    return values


@dataclass(frozen=True, slots=True)
class LinearFEMAssembly:
    nodes: Vector
    mass: Matrix
    stiffness: Matrix
    symmetry_linf: float


def assemble_linear_fem_1d(nodes: Sequence[Real]) -> LinearFEMAssembly:
    x = _nodes(nodes)
    n = len(x)
    mass = [[0.0] * n for _ in range(n)]
    stiffness = [[0.0] * n for _ in range(n)]
    for element in range(n - 1):
        h = x[element + 1] - x[element]
        local_mass = (
            (h / 3.0, h / 6.0),
            (h / 6.0, h / 3.0),
        )
        local_stiffness = (
            (1.0 / h, -1.0 / h),
            (-1.0 / h, 1.0 / h),
        )
        for local_i in range(2):
            for local_j in range(2):
                i = element + local_i
                j = element + local_j
                mass[i][j] += local_mass[local_i][local_j]
                stiffness[i][j] += local_stiffness[local_i][local_j]
    mass_matrix = tuple(tuple(row) for row in mass)
    stiffness_matrix = tuple(tuple(row) for row in stiffness)
    symmetry = max(
        max(
            abs(mass_matrix[i][j] - mass_matrix[j][i]),
            abs(stiffness_matrix[i][j] - stiffness_matrix[j][i]),
        )
        for i in range(n)
        for j in range(n)
    )
    return LinearFEMAssembly(
        nodes=x,
        mass=mass_matrix,
        stiffness=stiffness_matrix,
        symmetry_linf=symmetry,
    )


@dataclass(frozen=True, slots=True)
class FEMPoissonReport:
    nodes: Vector
    solution: Vector
    load: Vector
    algebraic_residual_linf: float
    boundary_residual_linf: float


def solve_poisson_fem_1d(
    nodes: Sequence[Real],
    forcing: ScalarFunction,
    *,
    left_boundary: Real = 0.0,
    right_boundary: Real = 0.0,
) -> FEMPoissonReport:
    assembly = assemble_linear_fem_1d(nodes)
    x = assembly.nodes
    n = len(x)
    left = finite_scalar("left_boundary", left_boundary)
    right = finite_scalar("right_boundary", right_boundary)
    load = [0.0] * n
    gauss = 1.0 / math.sqrt(3.0)

    for element in range(n - 1):
        a = x[element]
        b = x[element + 1]
        h = b - a
        midpoint = 0.5 * (a + b)
        radius = 0.5 * h
        for xi in (-gauss, gauss):
            point = midpoint + radius * xi
            value = finite_scalar("forcing_value", forcing(point))
            shape_left = 0.5 * (1.0 - xi)
            shape_right = 0.5 * (1.0 + xi)
            weight = radius
            load[element] += weight * value * shape_left
            load[element + 1] += weight * value * shape_right

    if n == 2:
        solution = (left, right)
    else:
        interior_count = n - 2
        system = tuple(
            tuple(assembly.stiffness[i + 1][j + 1] for j in range(interior_count))
            for i in range(interior_count)
        )
        rhs = []
        for i in range(1, n - 1):
            value = load[i]
            value -= assembly.stiffness[i][0] * left
            value -= assembly.stiffness[i][-1] * right
            rhs.append(value)
        interior = solve_linear_system(system, tuple(rhs)).solution
        solution = (left, *interior, right)

    residual = 0.0
    for i in range(1, n - 1):
        value = sum(assembly.stiffness[i][j] * solution[j] for j in range(n)) - load[i]
        residual = max(residual, abs(value))
    boundary_residual = max(abs(solution[0] - left), abs(solution[-1] - right))
    return FEMPoissonReport(
        nodes=x,
        solution=tuple(solution),
        load=tuple(load),
        algebraic_residual_linf=residual,
        boundary_residual_linf=boundary_residual,
    )
