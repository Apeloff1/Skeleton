"""Immutable dense tensor reference semantics with explicit broadcasting.

This is intentionally a correctness substrate rather than an accelerator.  Data
is flat row-major storage, shape is immutable, and every shape/index operation is
validated before arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from operator import mul
from typing import Callable, Iterable, Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector
from .numerics import compensated_sum


def _normalize_shape(shape: Sequence[int]) -> tuple[int, ...]:
    result: list[int] = []
    for index, dimension in enumerate(shape):
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise MathInvariantError(
                "tensor dimensions must be positive integers",
                reason="invalid_tensor_shape",
                field=f"shape[{index}]",
            )
        result.append(dimension)
    return tuple(result)


def _size(shape: Sequence[int]) -> int:
    result = 1
    for dimension in shape:
        result *= dimension
    return result


def _strides(shape: Sequence[int]) -> tuple[int, ...]:
    stride = 1
    output = [0] * len(shape)
    for index in range(len(shape) - 1, -1, -1):
        output[index] = stride
        stride *= shape[index]
    return tuple(output)


def _unravel(flat_index: int, shape: Sequence[int]) -> tuple[int, ...]:
    if not shape:
        return ()
    remaining = flat_index
    output: list[int] = []
    for stride, dimension in zip(_strides(shape), shape):
        coordinate = remaining // stride
        remaining %= stride
        if coordinate >= dimension:
            raise MathInvariantError(
                "flat tensor index is out of range",
                reason="tensor_index_out_of_range",
                field="index",
            )
        output.append(coordinate)
    return tuple(output)


def _ravel(indices: Sequence[int], shape: Sequence[int]) -> int:
    if len(indices) != len(shape):
        raise MathInvariantError(
            "tensor index rank mismatch",
            reason="dimension_mismatch",
            field="indices",
        )
    offset = 0
    for axis, (coordinate, dimension, stride) in enumerate(zip(indices, shape, _strides(shape))):
        if isinstance(coordinate, bool) or not isinstance(coordinate, int):
            raise MathInvariantError(
                "tensor indices must be integers",
                reason="invalid_tensor_index",
                field=f"indices[{axis}]",
            )
        if not 0 <= coordinate < dimension:
            raise MathInvariantError(
                "tensor index is out of range",
                reason="tensor_index_out_of_range",
                field=f"indices[{axis}]",
            )
        offset += coordinate * stride
    return offset


def broadcast_shape(left: Sequence[int], right: Sequence[int]) -> tuple[int, ...]:
    a = tuple(left)
    b = tuple(right)
    output: list[int] = []
    for index in range(1, max(len(a), len(b)) + 1):
        da = a[-index] if index <= len(a) else 1
        db = b[-index] if index <= len(b) else 1
        if da == db or da == 1 or db == 1:
            output.append(max(da, db))
        else:
            raise MathInvariantError(
                f"cannot broadcast dimensions {da} and {db}",
                reason="broadcast_mismatch",
                field="shape",
            )
    return tuple(reversed(output))


@dataclass(frozen=True, slots=True)
class DenseTensor:
    shape: tuple[int, ...]
    data: tuple[float, ...]

    def __post_init__(self) -> None:
        shape = _normalize_shape(self.shape)
        expected = _size(shape)
        values = finite_vector("data", self.data, allow_empty=False)
        if expected != len(values):
            raise MathInvariantError(
                f"tensor storage size {len(values)} != shape size {expected}",
                reason="tensor_storage_mismatch",
                field="data",
            )
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "data", values)

    @property
    def rank(self) -> int:
        return len(self.shape)

    @property
    def size(self) -> int:
        return len(self.data)

    @classmethod
    def scalar(cls, value: Real) -> "DenseTensor":
        # Scalars use a canonical singleton shape instead of rank-0 storage so all
        # public tensors retain at least one validated dimension.
        return cls((1,), (finite_scalar("value", value),))

    @classmethod
    def vector(cls, values: Sequence[Real] | Iterable[Real]) -> "DenseTensor":
        data = finite_vector("values", values)
        return cls((len(data),), data)

    @classmethod
    def matrix(cls, rows: Sequence[Sequence[Real]]) -> "DenseTensor":
        if not rows:
            raise MathInvariantError(
                "matrix tensor must not be empty",
                reason="empty_tensor",
                field="rows",
            )
        converted = tuple(finite_vector(f"rows[{index}]", row) for index, row in enumerate(rows))
        width = len(converted[0])
        if any(len(row) != width for row in converted):
            raise MathInvariantError(
                "matrix tensor rows must be rectangular",
                reason="ragged_matrix",
                field="rows",
            )
        return cls((len(converted), width), tuple(value for row in converted for value in row))

    @classmethod
    def zeros(cls, shape: Sequence[int]) -> "DenseTensor":
        normalized = _normalize_shape(shape)
        return cls(normalized, tuple(0.0 for _ in range(_size(normalized))))

    def get(self, *indices: int) -> float:
        return self.data[_ravel(indices, self.shape)]

    def reshape(self, shape: Sequence[int]) -> "DenseTensor":
        normalized = _normalize_shape(shape)
        if _size(normalized) != self.size:
            raise MathInvariantError(
                "reshape must preserve element count",
                reason="tensor_storage_mismatch",
                field="shape",
            )
        return DenseTensor(normalized, self.data)

    def transpose(self, axes: Sequence[int] | None = None) -> "DenseTensor":
        if axes is None:
            order = tuple(reversed(range(self.rank)))
        else:
            order = tuple(axes)
        if len(order) != self.rank or set(order) != set(range(self.rank)):
            raise MathInvariantError(
                "transpose axes must be a permutation of tensor axes",
                reason="invalid_axis_permutation",
                field="axes",
            )
        target_shape = tuple(self.shape[index] for index in order)
        output = [0.0] * self.size
        for flat_index, value in enumerate(self.data):
            source_index = _unravel(flat_index, self.shape)
            target_index = tuple(source_index[index] for index in order)
            output[_ravel(target_index, target_shape)] = value
        return DenseTensor(target_shape, tuple(output))

    def broadcast_to(self, shape: Sequence[int]) -> "DenseTensor":
        target = _normalize_shape(shape)
        if broadcast_shape(self.shape, target) != target:
            raise MathInvariantError(
                "target shape is not a valid broadcast result",
                reason="broadcast_mismatch",
                field="shape",
            )
        output: list[float] = []
        padding = len(target) - self.rank
        padded_shape = (1,) * padding + self.shape
        for flat_index in range(_size(target)):
            target_index = _unravel(flat_index, target)
            source_padded = tuple(
                0 if source_dim == 1 else coordinate
                for coordinate, source_dim in zip(target_index, padded_shape)
            )
            source_index = source_padded[padding:]
            output.append(self.get(*source_index))
        return DenseTensor(target, tuple(output))

    def map(self, function: Callable[[float], Real]) -> "DenseTensor":
        output = []
        for index, value in enumerate(self.data):
            output.append(finite_scalar(f"result[{index}]", function(value)))
        return DenseTensor(self.shape, tuple(output))

    def sum(self) -> float:
        return compensated_sum(self.data)

    def mean(self) -> float:
        return self.sum() / self.size


def tensor_zip(
    left: DenseTensor,
    right: DenseTensor,
    function: Callable[[float, float], Real],
) -> DenseTensor:
    target = broadcast_shape(left.shape, right.shape)
    a = left.broadcast_to(target) if left.shape != target else left
    b = right.broadcast_to(target) if right.shape != target else right
    output = tuple(
        finite_scalar(f"result[{index}]", function(x, y))
        for index, (x, y) in enumerate(zip(a.data, b.data))
    )
    return DenseTensor(target, output)


def add(left: DenseTensor, right: DenseTensor) -> DenseTensor:
    return tensor_zip(left, right, lambda a, b: a + b)


def subtract(left: DenseTensor, right: DenseTensor) -> DenseTensor:
    return tensor_zip(left, right, lambda a, b: a - b)


def multiply(left: DenseTensor, right: DenseTensor) -> DenseTensor:
    return tensor_zip(left, right, mul)


def divide(left: DenseTensor, right: DenseTensor) -> DenseTensor:
    def operation(a: float, b: float) -> float:
        if b == 0.0:
            raise MathInvariantError(
                "tensor division by zero",
                reason="division_by_zero",
                field="right",
            )
        return a / b

    return tensor_zip(left, right, operation)


def reduce_sum(tensor: DenseTensor, axis: int) -> DenseTensor:
    if isinstance(axis, bool) or not isinstance(axis, int):
        raise MathInvariantError(
            "reduction axis must be an integer",
            reason="invalid_axis",
            field="axis",
        )
    normalized_axis = axis if axis >= 0 else tensor.rank + axis
    if not 0 <= normalized_axis < tensor.rank:
        raise MathInvariantError(
            "reduction axis is out of range",
            reason="invalid_axis",
            field="axis",
        )
    target_shape = tuple(
        dimension
        for index, dimension in enumerate(tensor.shape)
        if index != normalized_axis
    )
    # Preserve an explicit singleton dimension for a full vector reduction.
    if not target_shape:
        return DenseTensor.scalar(tensor.sum())
    output = [0.0] * _size(target_shape)
    buckets: list[list[float]] = [[] for _ in output]
    for flat_index, value in enumerate(tensor.data):
        index = _unravel(flat_index, tensor.shape)
        target_index = tuple(
            coordinate
            for axis_index, coordinate in enumerate(index)
            if axis_index != normalized_axis
        )
        buckets[_ravel(target_index, target_shape)].append(value)
    for index, bucket in enumerate(buckets):
        output[index] = compensated_sum(bucket)
    return DenseTensor(target_shape, tuple(output))


def reduce_mean(tensor: DenseTensor, axis: int) -> DenseTensor:
    if isinstance(axis, bool) or not isinstance(axis, int):
        raise MathInvariantError(
            "reduction axis must be an integer",
            reason="invalid_axis",
            field="axis",
        )
    normalized_axis = axis if axis >= 0 else tensor.rank + axis
    if not 0 <= normalized_axis < tensor.rank:
        raise MathInvariantError(
            "reduction axis is out of range",
            reason="invalid_axis",
            field="axis",
        )
    count = tensor.shape[normalized_axis]
    return reduce_sum(tensor, normalized_axis).map(lambda value: value / count)
