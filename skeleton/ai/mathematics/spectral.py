"""Spectral reference methods for matrix and sequence diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import dot, l2_norm, matvec
from .numerics import compensated_sum, stable_mean


@dataclass(frozen=True, slots=True)
class EigenReport:
    eigenvalue: float
    eigenvector: Vector
    residual_l2: float
    iterations: int
    converged: bool


@dataclass(frozen=True, slots=True)
class SpectrumBin:
    bin_index: int
    frequency: float
    real: float
    imag: float
    power: float


def _canonical_sign(vector: Vector) -> Vector:
    pivot = max(range(len(vector)), key=lambda index: abs(vector[index]))
    if vector[pivot] < 0.0:
        return tuple(-value for value in vector)
    return vector


def dominant_eigenpair_symmetric(
    matrix: Sequence[Sequence[Real]],
    *,
    max_iterations: int = 1000,
    tolerance: Real = 1e-12,
    symmetry_tolerance: Real = 1e-12,
) -> EigenReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "eigen decomposition requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    tol = positive_scalar("tolerance", tolerance)
    sym_tol = positive_scalar("symmetry_tolerance", symmetry_tolerance)
    scale = max(1.0, max(abs(value) for row in source for value in row))
    for row in range(n):
        for column in range(row + 1, n):
            if abs(source[row][column] - source[column][row]) > sym_tol * scale:
                raise MathInvariantError(
                    "dominant_eigenpair_symmetric requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )

    seed = tuple(1.0 / (index + 1.0) for index in range(n))
    seed_norm = l2_norm(seed)
    vector = tuple(value / seed_norm for value in seed)
    eigenvalue = dot(vector, matvec(source, vector))

    for iteration in range(1, max_iterations + 1):
        product = matvec(source, vector)
        norm = l2_norm(product)
        if norm == 0.0:
            raise MathInvariantError(
                "power iteration reached a zero image",
                reason="zero_eigenspace_image",
                field="matrix",
            )
        candidate = tuple(value / norm for value in product)
        candidate = _canonical_sign(candidate)
        candidate_value = dot(candidate, matvec(source, candidate))
        delta = min(
            l2_norm(tuple(a - b for a, b in zip(candidate, vector))),
            l2_norm(tuple(a + b for a, b in zip(candidate, vector))),
        )
        vector = candidate
        eigenvalue = candidate_value
        residual_vector = tuple(
            left - eigenvalue * right
            for left, right in zip(matvec(source, vector), vector)
        )
        residual = l2_norm(residual_vector)
        if delta <= tol and residual <= max(tol, tol * abs(eigenvalue)):
            return EigenReport(
                eigenvalue=eigenvalue,
                eigenvector=vector,
                residual_l2=residual,
                iterations=iteration,
                converged=True,
            )

    residual_vector = tuple(
        left - eigenvalue * right
        for left, right in zip(matvec(source, vector), vector)
    )
    return EigenReport(
        eigenvalue=eigenvalue,
        eigenvector=vector,
        residual_l2=l2_norm(residual_vector),
        iterations=max_iterations,
        converged=False,
    )


def periodogram(
    values: Sequence[Real],
    *,
    sample_spacing: Real = 1.0,
    detrend: bool = True,
) -> tuple[SpectrumBin, ...]:
    observations = finite_vector("values", values)
    if len(observations) < 2:
        raise MathInvariantError(
            "periodogram requires at least two observations",
            reason="insufficient_observations",
            field="values",
        )
    spacing = positive_scalar("sample_spacing", sample_spacing)
    mean = stable_mean(observations) if detrend else 0.0
    centered = tuple(value - mean for value in observations)
    n = len(centered)
    bins: list[SpectrumBin] = []
    for bin_index in range(n // 2 + 1):
        real = 0.0
        imag = 0.0
        for time_index, value in enumerate(centered):
            angle = 2.0 * math.pi * bin_index * time_index / n
            real += value * math.cos(angle)
            imag -= value * math.sin(angle)
        power = (real * real + imag * imag) / (n * n)
        bins.append(
            SpectrumBin(
                bin_index=bin_index,
                frequency=bin_index / (n * spacing),
                real=real / n,
                imag=imag / n,
                power=power,
            )
        )
    return tuple(bins)


def dominant_frequency(
    values: Sequence[Real],
    *,
    sample_spacing: Real = 1.0,
) -> SpectrumBin:
    bins = periodogram(values, sample_spacing=sample_spacing, detrend=True)
    candidates = bins[1:]  # exclude DC after detrending
    if not candidates:
        raise MathInvariantError(
            "no non-zero frequency bins are available",
            reason="insufficient_observations",
            field="values",
        )
    return max(candidates, key=lambda item: (item.power, -item.bin_index))


def spectral_power_fraction(
    values: Sequence[Real],
    selected_bins: Sequence[int],
    *,
    sample_spacing: Real = 1.0,
) -> float:
    spectrum = periodogram(values, sample_spacing=sample_spacing, detrend=True)
    indices = set()
    for index in selected_bins:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(spectrum):
            raise MathInvariantError(
                "selected spectrum bin is out of range",
                reason="invalid_spectrum_bin",
                field="selected_bins",
            )
        indices.add(index)
    total = compensated_sum(item.power for item in spectrum)
    if total == 0.0:
        return 0.0
    selected = compensated_sum(item.power for item in spectrum if item.bin_index in indices)
    return selected / total
