"""HOSVD/Tucker dense-tensor decomposition reference semantics."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector
from .numerics import compensated_sum
from .svd import singular_value_decomposition
from .tensor import DenseTensor
from .tensor_contract import mode_product


def unfold_tensor(tensor: DenseTensor, axis: int) -> Matrix:
    normalized = axis if axis >= 0 else tensor.rank + axis
    if not 0 <= normalized < tensor.rank:
        raise MathInvariantError(
            "tensor unfolding axis is out of range",
            reason="invalid_axis",
            field="axis",
        )
    free_axes = tuple(index for index in range(tensor.rank) if index != normalized)
    free_ranges = tuple(range(tensor.shape[index]) for index in free_axes)
    rows = []
    for coordinate in range(tensor.shape[normalized]):
        row = []
        for free_coordinate in itertools.product(*free_ranges):
            index = [0] * tensor.rank
            index[normalized] = coordinate
            for free_axis, value in zip(free_axes, free_coordinate):
                index[free_axis] = value
            row.append(tensor.get(*index))
        rows.append(tuple(row))
    return tuple(rows)


def _factor_matrix(left_vectors: Matrix, rank: int, dimension: int) -> Matrix:
    return tuple(
        tuple(left_vectors[column][row] for column in range(rank))
        for row in range(dimension)
    )


def _transpose(matrix: Matrix) -> Matrix:
    return tuple(
        tuple(matrix[row][column] for row in range(len(matrix)))
        for column in range(len(matrix[0]))
    )


def tucker_reconstruct(
    core: DenseTensor,
    factors: Sequence[Matrix],
) -> DenseTensor:
    if len(factors) != core.rank:
        raise MathInvariantError(
            "Tucker factor count must match core rank",
            reason="dimension_mismatch",
            field="factors",
        )
    result = core
    for axis, factor in enumerate(factors):
        if not factor or not factor[0] or len(factor[0]) != result.shape[axis]:
            raise MathInvariantError(
                "Tucker factor columns must match current core mode size",
                reason="dimension_mismatch",
                field=f"factors[{axis}]",
            )
        result = mode_product(result, DenseTensor.matrix(factor), axis)
    return result


@dataclass(frozen=True, slots=True)
class HOSVDReport:
    core: DenseTensor
    factors: tuple[Matrix, ...]
    ranks: tuple[int, ...]
    singular_values: tuple[Vector, ...]
    axis_retained_energy: Vector
    reconstruction: DenseTensor
    residual_frobenius: float
    relative_residual_frobenius: float


def hosvd(
    tensor: DenseTensor,
    ranks: Sequence[int] | None = None,
) -> HOSVDReport:
    if ranks is not None and len(ranks) != tensor.rank:
        raise MathInvariantError(
            "HOSVD rank count must match tensor rank",
            reason="dimension_mismatch",
            field="ranks",
        )
    factors = []
    singular_values = []
    retained = []
    chosen_ranks = []

    for axis in range(tensor.rank):
        svd = singular_value_decomposition(unfold_tensor(tensor, axis))
        if svd.rank < 1:
            raise MathInvariantError(
                "HOSVD cannot decompose a numerically zero unfolding",
                reason="zero_norm",
                field=f"axis[{axis}]",
            )
        requested = svd.rank if ranks is None else ranks[axis]
        if isinstance(requested, bool) or not isinstance(requested, int) or not 1 <= requested <= svd.rank:
            raise MathInvariantError(
                "requested HOSVD rank must lie within numerical unfolding rank",
                reason="invalid_rank",
                field=f"ranks[{axis}]",
            )
        factor = _factor_matrix(svd.left_vectors, requested, tensor.shape[axis])
        factors.append(factor)
        singular_values.append(svd.singular_values)
        chosen_ranks.append(requested)
        total = compensated_sum(value * value for value in svd.singular_values)
        kept = compensated_sum(svd.singular_values[index] ** 2 for index in range(requested))
        retained.append(kept / total if total else 1.0)

    core = tensor
    for axis, factor in enumerate(factors):
        core = mode_product(core, DenseTensor.matrix(_transpose(factor)), axis)
    reconstruction = tucker_reconstruct(core, tuple(factors))
    residual_squared = compensated_sum(
        (source - restored) ** 2
        for source, restored in zip(tensor.data, reconstruction.data)
    )
    source_squared = compensated_sum(value * value for value in tensor.data)
    residual = math.sqrt(max(0.0, residual_squared))
    return HOSVDReport(
        core=core,
        factors=tuple(factors),
        ranks=tuple(chosen_ranks),
        singular_values=tuple(singular_values),
        axis_retained_energy=tuple(retained),
        reconstruction=reconstruction,
        residual_frobenius=residual,
        relative_residual_frobenius=0.0 if source_squared == 0.0 else residual / math.sqrt(source_squared),
    )
