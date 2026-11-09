"""Linear-Gaussian Kalman filtering and Rauch-Tung-Striebel smoothing."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector
from .linear import matmul, matvec, transpose
from .lu import matrix_inverse
from .matrix_algebra2 import identity_matrix
from .numerics import compensated_sum


def _add(left: Matrix, right: Matrix) -> Matrix:
    if len(left) != len(right) or len(left[0]) != len(right[0]):
        raise MathInvariantError(
            "matrix addition dimension mismatch",
            reason="dimension_mismatch",
            field="matrix",
        )
    return tuple(
        tuple(a + b for a, b in zip(left_row, right_row))
        for left_row, right_row in zip(left, right)
    )


def _subtract(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(a - b for a, b in zip(left_row, right_row))
        for left_row, right_row in zip(left, right)
    )


def _symmetrize(matrix: Matrix) -> Matrix:
    n = len(matrix)
    return tuple(
        tuple(0.5 * (matrix[i][j] + matrix[j][i]) for j in range(n))
        for i in range(n)
    )


@dataclass(frozen=True, slots=True)
class KalmanState:
    mean: Vector
    covariance: Matrix


@dataclass(frozen=True, slots=True)
class KalmanStep:
    predicted: KalmanState
    filtered: KalmanState
    innovation: Vector
    innovation_covariance: Matrix
    kalman_gain: Matrix
    innovation_mahalanobis_squared: float


@dataclass(frozen=True, slots=True)
class KalmanFilterReport:
    steps: tuple[KalmanStep, ...]
    final_state: KalmanState


@dataclass(frozen=True, slots=True)
class RTSSmootherReport:
    filtered_states: tuple[KalmanState, ...]
    smoothed_states: tuple[KalmanState, ...]
    smoothing_gains: tuple[Matrix, ...]


def _validate_model(
    transition: Sequence[Sequence[Real]],
    observation: Sequence[Sequence[Real]],
    process_covariance: Sequence[Sequence[Real]],
    observation_covariance: Sequence[Sequence[Real]],
) -> tuple[Matrix, Matrix, Matrix, Matrix]:
    f = finite_matrix("transition", transition)
    h = finite_matrix("observation", observation)
    q = finite_matrix("process_covariance", process_covariance)
    r = finite_matrix("observation_covariance", observation_covariance)
    n = len(f)
    if len(f[0]) != n or len(q) != n or len(q[0]) != n:
        raise MathInvariantError(
            "Kalman transition/process covariance dimensions must be square and aligned",
            reason="dimension_mismatch",
            field="state_model",
        )
    m = len(h)
    if len(h[0]) != n or len(r) != m or len(r[0]) != m:
        raise MathInvariantError(
            "Kalman observation covariance dimensions must align with observation rows",
            reason="dimension_mismatch",
            field="observation_model",
        )
    return f, h, q, r


def kalman_filter(
    measurements: Sequence[Sequence[Real]],
    *,
    initial_mean: Sequence[Real],
    initial_covariance: Sequence[Sequence[Real]],
    transition: Sequence[Sequence[Real]],
    observation: Sequence[Sequence[Real]],
    process_covariance: Sequence[Sequence[Real]],
    observation_covariance: Sequence[Sequence[Real]],
) -> KalmanFilterReport:
    f, h, q, r = _validate_model(
        transition,
        observation,
        process_covariance,
        observation_covariance,
    )
    mean = finite_vector("initial_mean", initial_mean)
    covariance = finite_matrix("initial_covariance", initial_covariance)
    n = len(f)
    m = len(h)
    if len(mean) != n or len(covariance) != n or len(covariance[0]) != n:
        raise MathInvariantError(
            "Kalman initial state dimensions do not match transition",
            reason="dimension_mismatch",
            field="initial_state",
        )
    clean_measurements = tuple(
        finite_vector(f"measurements[{index}]", measurement)
        for index, measurement in enumerate(measurements)
    )
    if not clean_measurements or any(len(measurement) != m for measurement in clean_measurements):
        raise MathInvariantError(
            "Kalman measurements must be non-empty and match observation dimension",
            reason="dimension_mismatch",
            field="measurements",
        )

    identity = identity_matrix(n)
    steps: list[KalmanStep] = []
    for measurement in clean_measurements:
        predicted_mean = matvec(f, mean)
        predicted_covariance = _add(matmul(matmul(f, covariance), transpose(f)), q)
        innovation = tuple(
            measurement[i] - value
            for i, value in enumerate(matvec(h, predicted_mean))
        )
        innovation_covariance = _add(
            matmul(matmul(h, predicted_covariance), transpose(h)),
            r,
        )
        innovation_inverse = matrix_inverse(innovation_covariance).inverse
        gain = matmul(matmul(predicted_covariance, transpose(h)), innovation_inverse)
        correction = matvec(gain, innovation)
        filtered_mean = tuple(predicted_mean[i] + correction[i] for i in range(n))

        kh = matmul(gain, h)
        left = _subtract(identity, kh)
        # Joseph stabilized covariance: (I-KH)P(I-KH)^T + K R K^T.
        filtered_covariance = _add(
            matmul(matmul(left, predicted_covariance), transpose(left)),
            matmul(matmul(gain, r), transpose(gain)),
        )
        filtered_covariance = _symmetrize(filtered_covariance)
        mahalanobis = compensated_sum(
            innovation[i] * value
            for i, value in enumerate(matvec(innovation_inverse, innovation))
        )
        predicted_state = KalmanState(predicted_mean, predicted_covariance)
        filtered_state = KalmanState(filtered_mean, filtered_covariance)
        steps.append(
            KalmanStep(
                predicted=predicted_state,
                filtered=filtered_state,
                innovation=innovation,
                innovation_covariance=innovation_covariance,
                kalman_gain=gain,
                innovation_mahalanobis_squared=mahalanobis,
            )
        )
        mean, covariance = filtered_mean, filtered_covariance

    return KalmanFilterReport(tuple(steps), KalmanState(mean, covariance))


def rts_smooth(
    filter_report: KalmanFilterReport,
    transition: Sequence[Sequence[Real]],
) -> RTSSmootherReport:
    f = finite_matrix("transition", transition)
    if not filter_report.steps:
        raise MathInvariantError(
            "RTS smoothing requires at least one filtered step",
            reason="insufficient_observations",
            field="filter_report",
        )
    n = len(f)
    if len(f[0]) != n:
        raise MathInvariantError(
            "RTS transition must be square",
            reason="non_square_matrix",
            field="transition",
        )
    filtered = tuple(step.filtered for step in filter_report.steps)
    smoothed = list(filtered)
    gains: list[Matrix] = [identity_matrix(n) for _ in range(max(0, len(filtered) - 1))]

    for index in range(len(filtered) - 2, -1, -1):
        filtered_state = filtered[index]
        next_prediction = filter_report.steps[index + 1].predicted
        inverse_prediction = matrix_inverse(next_prediction.covariance).inverse
        gain = matmul(
            matmul(filtered_state.covariance, transpose(f)),
            inverse_prediction,
        )
        gains[index] = gain
        mean_delta = tuple(
            smoothed[index + 1].mean[i] - next_prediction.mean[i]
            for i in range(n)
        )
        smooth_mean = tuple(
            filtered_state.mean[i] + value
            for i, value in enumerate(matvec(gain, mean_delta))
        )
        covariance_delta = _subtract(
            smoothed[index + 1].covariance,
            next_prediction.covariance,
        )
        smooth_covariance = _add(
            filtered_state.covariance,
            matmul(matmul(gain, covariance_delta), transpose(gain)),
        )
        smoothed[index] = KalmanState(smooth_mean, _symmetrize(smooth_covariance))

    return RTSSmootherReport(
        filtered_states=filtered,
        smoothed_states=tuple(smoothed),
        smoothing_gains=tuple(gains),
    )
