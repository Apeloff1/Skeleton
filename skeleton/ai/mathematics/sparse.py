"""Canonical sparse linear-algebra reference semantics.

The representation is immutable CSR with sorted unique column indices in every
row.  Construction from COO deterministically merges duplicate coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector
from .numerics import compensated_sum


def _shape(shape: Sequence[int]) -> tuple[int, int]:
    if len(shape) != 2:
        raise MathInvariantError(
            "sparse matrix shape must have rank two",
            reason="invalid_sparse_shape",
            field="shape",
        )
    rows, columns = shape
    for index, value in enumerate((rows, columns)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise MathInvariantError(
                "sparse matrix dimensions must be positive integers",
                reason="invalid_sparse_shape",
                field=f"shape[{index}]",
            )
    return rows, columns


@dataclass(frozen=True, slots=True)
class CSRMatrix:
    shape: tuple[int, int]
    indptr: tuple[int, ...]
    indices: tuple[int, ...]
    data: tuple[float, ...]

    def __post_init__(self) -> None:
        rows, columns = _shape(self.shape)
        if len(self.indptr) != rows + 1:
            raise MathInvariantError(
                "CSR indptr length must equal rows + 1",
                reason="invalid_csr_structure",
                field="indptr",
            )
        if not self.indptr or self.indptr[0] != 0:
            raise MathInvariantError(
                "CSR indptr must start at zero",
                reason="invalid_csr_structure",
                field="indptr",
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.indptr
        ):
            raise MathInvariantError(
                "CSR indptr entries must be non-negative integers",
                reason="invalid_csr_structure",
                field="indptr",
            )
        if any(left > right for left, right in zip(self.indptr, self.indptr[1:])):
            raise MathInvariantError(
                "CSR indptr must be non-decreasing",
                reason="invalid_csr_structure",
                field="indptr",
            )
        if self.indptr[-1] != len(self.indices) or len(self.indices) != len(self.data):
            raise MathInvariantError(
                "CSR storage lengths are inconsistent",
                reason="invalid_csr_structure",
                field="data",
            )
        clean_data = tuple(
            finite_scalar(f"data[{index}]", value)
            for index, value in enumerate(self.data)
        )
        for row in range(rows):
            start, end = self.indptr[row], self.indptr[row + 1]
            previous = -1
            for offset in range(start, end):
                column = self.indices[offset]
                if isinstance(column, bool) or not isinstance(column, int) or not 0 <= column < columns:
                    raise MathInvariantError(
                        "CSR column index is out of range",
                        reason="sparse_index_out_of_range",
                        field=f"indices[{offset}]",
                    )
                if column <= previous:
                    raise MathInvariantError(
                        "CSR row indices must be strictly increasing and unique",
                        reason="noncanonical_csr",
                        field=f"indices[{offset}]",
                    )
                previous = column
        object.__setattr__(self, "shape", (rows, columns))
        object.__setattr__(self, "data", clean_data)

    @property
    def nnz(self) -> int:
        return len(self.data)

    @property
    def density(self) -> float:
        rows, columns = self.shape
        return self.nnz / (rows * columns)

    @classmethod
    def from_dense(
        cls,
        matrix: Sequence[Sequence[Real]],
        *,
        zero_tolerance: Real = 0.0,
    ) -> "CSRMatrix":
        if not matrix:
            raise MathInvariantError(
                "dense source must not be empty",
                reason="empty_matrix",
                field="matrix",
            )
        rows = tuple(finite_vector(f"matrix[{index}]", row) for index, row in enumerate(matrix))
        columns = len(rows[0])
        if any(len(row) != columns for row in rows):
            raise MathInvariantError(
                "dense source must be rectangular",
                reason="ragged_matrix",
                field="matrix",
            )
        tolerance = finite_scalar("zero_tolerance", zero_tolerance)
        if tolerance < 0.0:
            raise MathInvariantError(
                "zero_tolerance must be non-negative",
                reason="negative_tolerance",
                field="zero_tolerance",
            )
        indptr = [0]
        indices: list[int] = []
        data: list[float] = []
        for row in rows:
            for column, value in enumerate(row):
                if abs(value) > tolerance:
                    indices.append(column)
                    data.append(value)
            indptr.append(len(indices))
        return cls(
            shape=(len(rows), columns),
            indptr=tuple(indptr),
            indices=tuple(indices),
            data=tuple(data),
        )

    @classmethod
    def from_coo(
        cls,
        shape: Sequence[int],
        row_indices: Sequence[int],
        column_indices: Sequence[int],
        values: Sequence[Real],
    ) -> "CSRMatrix":
        rows, columns = _shape(shape)
        if not (len(row_indices) == len(column_indices) == len(values)):
            raise MathInvariantError(
                "COO coordinate arrays must have equal length",
                reason="dimension_mismatch",
                field="coo",
            )
        buckets: list[dict[int, list[float]]] = [dict() for _ in range(rows)]
        for offset, (row, column, value) in enumerate(zip(row_indices, column_indices, values)):
            if isinstance(row, bool) or not isinstance(row, int) or not 0 <= row < rows:
                raise MathInvariantError(
                    "COO row index is out of range",
                    reason="sparse_index_out_of_range",
                    field=f"row_indices[{offset}]",
                )
            if isinstance(column, bool) or not isinstance(column, int) or not 0 <= column < columns:
                raise MathInvariantError(
                    "COO column index is out of range",
                    reason="sparse_index_out_of_range",
                    field=f"column_indices[{offset}]",
                )
            scalar = finite_scalar(f"values[{offset}]", value)
            buckets[row].setdefault(column, []).append(scalar)

        indptr = [0]
        indices: list[int] = []
        data: list[float] = []
        for bucket in buckets:
            for column in sorted(bucket):
                value = compensated_sum(bucket[column])
                if value != 0.0:
                    indices.append(column)
                    data.append(value)
            indptr.append(len(indices))
        return cls((rows, columns), tuple(indptr), tuple(indices), tuple(data))

    def to_dense(self) -> Matrix:
        rows, columns = self.shape
        output = [[0.0] * columns for _ in range(rows)]
        for row in range(rows):
            for offset in range(self.indptr[row], self.indptr[row + 1]):
                output[row][self.indices[offset]] = self.data[offset]
        return tuple(tuple(row) for row in output)

    def matvec(self, vector: Sequence[Real]) -> Vector:
        values = finite_vector("vector", vector)
        rows, columns = self.shape
        if len(values) != columns:
            raise MathInvariantError(
                "sparse matvec dimension mismatch",
                reason="dimension_mismatch",
                field="vector",
            )
        output = []
        for row in range(rows):
            output.append(
                compensated_sum(
                    self.data[offset] * values[self.indices[offset]]
                    for offset in range(self.indptr[row], self.indptr[row + 1])
                )
            )
        return tuple(output)

    def transpose(self) -> "CSRMatrix":
        rows, _ = self.shape
        row_indices: list[int] = []
        column_indices: list[int] = []
        values: list[float] = []
        for row in range(rows):
            for offset in range(self.indptr[row], self.indptr[row + 1]):
                row_indices.append(self.indices[offset])
                column_indices.append(row)
                values.append(self.data[offset])
        return CSRMatrix.from_coo(
            (self.shape[1], self.shape[0]),
            row_indices,
            column_indices,
            values,
        )

    def row(self, index: int) -> Vector:
        rows, columns = self.shape
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < rows:
            raise MathInvariantError(
                "sparse row index is out of range",
                reason="sparse_index_out_of_range",
                field="index",
            )
        output = [0.0] * columns
        for offset in range(self.indptr[index], self.indptr[index + 1]):
            output[self.indices[offset]] = self.data[offset]
        return tuple(output)


def sparse_dense_matmul(
    left: CSRMatrix,
    right: Sequence[Sequence[Real]],
) -> Matrix:
    if not right:
        raise MathInvariantError(
            "right matrix must not be empty",
            reason="empty_matrix",
            field="right",
        )
    matrix = tuple(finite_vector(f"right[{index}]", row) for index, row in enumerate(right))
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise MathInvariantError(
            "right matrix must be rectangular",
            reason="ragged_matrix",
            field="right",
        )
    if left.shape[1] != len(matrix):
        raise MathInvariantError(
            "sparse-dense matmul dimension mismatch",
            reason="dimension_mismatch",
            field="right",
        )
    output: list[tuple[float, ...]] = []
    for row in range(left.shape[0]):
        result_row = []
        for column in range(width):
            result_row.append(
                compensated_sum(
                    left.data[offset] * matrix[left.indices[offset]][column]
                    for offset in range(left.indptr[row], left.indptr[row + 1])
                )
            )
        output.append(tuple(result_row))
    return tuple(output)
