"""General dense tensor contraction reference semantics."""
from __future__ import annotations

from itertools import product
from typing import Sequence

from .contracts import MathInvariantError
from .numerics import compensated_sum
from .tensor import DenseTensor


def _axes(rank: int, axes: Sequence[int], name: str) -> tuple[int, ...]:
    normalized: list[int] = []
    for position, axis in enumerate(axes):
        if isinstance(axis, bool) or not isinstance(axis, int):
            raise MathInvariantError(
                "tensor contraction axes must be integers",
                reason="invalid_axis",
                field=f"{name}[{position}]",
            )
        value = axis if axis >= 0 else rank + axis
        if not 0 <= value < rank:
            raise MathInvariantError(
                "tensor contraction axis is out of range",
                reason="invalid_axis",
                field=f"{name}[{position}]",
            )
        if value in normalized:
            raise MathInvariantError(
                "tensor contraction axes must be unique",
                reason="duplicate_axis",
                field=name,
            )
        normalized.append(value)
    return tuple(normalized)


def tensor_contract(
    left: DenseTensor,
    right: DenseTensor,
    *,
    left_axes: Sequence[int],
    right_axes: Sequence[int],
) -> DenseTensor:
    a_axes = _axes(left.rank, left_axes, "left_axes")
    b_axes = _axes(right.rank, right_axes, "right_axes")
    if len(a_axes) != len(b_axes):
        raise MathInvariantError(
            "left and right contraction axis lists must have equal length",
            reason="dimension_mismatch",
            field="axes",
        )
    for left_axis, right_axis in zip(a_axes, b_axes):
        if left.shape[left_axis] != right.shape[right_axis]:
            raise MathInvariantError(
                "contracted tensor dimensions must match",
                reason="dimension_mismatch",
                field="axes",
            )

    left_free = tuple(axis for axis in range(left.rank) if axis not in a_axes)
    right_free = tuple(axis for axis in range(right.rank) if axis not in b_axes)
    output_shape = tuple(left.shape[axis] for axis in left_free) + tuple(
        right.shape[axis] for axis in right_free
    )
    contraction_shape = tuple(left.shape[axis] for axis in a_axes)

    left_ranges = [range(left.shape[axis]) for axis in left_free]
    right_ranges = [range(right.shape[axis]) for axis in right_free]
    contraction_ranges = [range(size) for size in contraction_shape]

    output_values: list[float] = []
    output_coordinates = product(
        *left_ranges,
        *right_ranges,
    ) if output_shape else [()]

    for coordinate in output_coordinates:
        left_free_values = coordinate[: len(left_free)]
        right_free_values = coordinate[len(left_free):]
        terms: list[float] = []
        contracted_coordinates = product(*contraction_ranges) if contraction_shape else [()]
        for contracted in contracted_coordinates:
            left_index = [0] * left.rank
            right_index = [0] * right.rank
            for axis, value in zip(left_free, left_free_values):
                left_index[axis] = value
            for axis, value in zip(right_free, right_free_values):
                right_index[axis] = value
            for axis, value in zip(a_axes, contracted):
                left_index[axis] = value
            for axis, value in zip(b_axes, contracted):
                right_index[axis] = value
            terms.append(left.get(*left_index) * right.get(*right_index))
        output_values.append(compensated_sum(terms))

    if not output_shape:
        return DenseTensor.scalar(output_values[0])
    return DenseTensor(output_shape, tuple(output_values))


def tensor_outer(left: DenseTensor, right: DenseTensor) -> DenseTensor:
    return tensor_contract(left, right, left_axes=(), right_axes=())


def tensor_dot(left: DenseTensor, right: DenseTensor) -> float:
    if left.shape != right.shape:
        raise MathInvariantError(
            "tensor dot product requires equal shapes",
            reason="dimension_mismatch",
            field="shape",
        )
    contracted = tensor_contract(
        left,
        right,
        left_axes=tuple(range(left.rank)),
        right_axes=tuple(range(right.rank)),
    )
    return contracted.data[0]


def mode_product(
    tensor: DenseTensor,
    matrix: DenseTensor,
    axis: int,
) -> DenseTensor:
    if matrix.rank != 2:
        raise MathInvariantError(
            "mode product matrix must be rank two",
            reason="dimension_mismatch",
            field="matrix",
        )
    normalized = axis if axis >= 0 else tensor.rank + axis
    if not 0 <= normalized < tensor.rank:
        raise MathInvariantError(
            "mode product axis is out of range",
            reason="invalid_axis",
            field="axis",
        )
    if matrix.shape[1] != tensor.shape[normalized]:
        raise MathInvariantError(
            "mode product matrix width must match selected tensor dimension",
            reason="dimension_mismatch",
            field="matrix",
        )
    # Matrix contracts its column dimension with the chosen tensor axis.
    raw = tensor_contract(
        matrix,
        tensor,
        left_axes=(1,),
        right_axes=(normalized,),
    )
    # Raw shape is (new_mode, tensor free axes...). Move new_mode back to axis.
    target_order = list(range(1, raw.rank))
    target_order.insert(normalized, 0)
    return raw.transpose(target_order)
