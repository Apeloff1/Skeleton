"""Leakage-safe empirical calibrator for Dragon heuristic belief scores.

Fits a monotonic histogram calibrator only from labelled training periods and
evaluates it on disjoint held-out periods. This deliberately simple model is
auditable and deterministic; insufficient bins fall back to the global base
rate and are surfaced in the artifact.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite

from .dragon_probability_calibration import (
    CalibrationExample, CalibrationReport, calibration_report,
)


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    samples: int
    observed_rate: float


@dataclass(frozen=True)
class CalibrationArtifact:
    bins: tuple[CalibrationBin, ...]
    training_periods: tuple[str, ...]
    evaluation_periods: tuple[str, ...]
    training_samples: int
    evaluation: CalibrationReport
    artifact_fingerprint: str
    eligible: bool
    warnings: tuple[str, ...]


def _validate_periods(train: tuple[str, ...], evaluation: tuple[str, ...]) -> None:
    if not train or not evaluation:
        raise ValueError("training and evaluation periods are required")
    if len(set(train)) != len(train) or len(set(evaluation)) != len(evaluation):
        raise ValueError("duplicate period")
    if set(train) & set(evaluation):
        raise ValueError("calibration period leakage")


def fit_histogram_calibrator(
    examples: tuple[CalibrationExample, ...], *,
    training_periods: tuple[str, ...],
    evaluation_periods: tuple[str, ...],
    authorized: bool,
    bins: int = 10,
    minimum_bin_samples: int = 10,
    minimum_evaluation_samples: int = 30,
    maximum_ece: float = .10,
) -> CalibrationArtifact:
    if not authorized:
        raise PermissionError("calibrator fitting requires authorization")
    _validate_periods(training_periods, evaluation_periods)
    if not 2 <= bins <= 100 or not 1 <= minimum_bin_samples <= 100000:
        raise ValueError("invalid calibration bin policy")
    if not 1 <= minimum_evaluation_samples <= 100000:
        raise ValueError("invalid evaluation sample policy")
    if not isfinite(maximum_ece) or not 0 <= maximum_ece <= 1:
        raise ValueError("invalid ECE threshold")
    allowed = set(training_periods) | set(evaluation_periods)
    rows = tuple(x for x in examples if x.period in allowed)
    train = tuple(x for x in rows if x.period in training_periods)
    heldout = tuple(x for x in rows if x.period in evaluation_periods)
    if not train or not heldout:
        raise ValueError("both training and held-out labels are required")
    # Reuse strict validation and duplicate checks.
    calibration_report(train, authorized=True, minimum_samples=1)
    calibration_report(heldout, authorized=True, minimum_samples=1)
    global_rate = sum(int(x.observed_truth) for x in train) / len(train)
    learned = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        bucket = tuple(x for x in train if (
            lower <= x.predicted_probability < upper or
            (index == bins - 1 and x.predicted_probability == 1)
        ))
        rate = (
            sum(int(x.observed_truth) for x in bucket) / len(bucket)
            if len(bucket) >= minimum_bin_samples else global_rate
        )
        learned.append(CalibrationBin(
            lower, upper, len(bucket), round(rate, 8),
        ))
    def transform(x: CalibrationExample) -> CalibrationExample:
        index = min(bins - 1, int(x.predicted_probability * bins))
        return CalibrationExample(
            x.claim_id, learned[index].observed_rate, x.observed_truth,
            x.source_group, x.period,
        )
    calibrated_heldout = tuple(transform(x) for x in heldout)
    evaluation = calibration_report(
        calibrated_heldout, authorized=True,
        minimum_samples=minimum_evaluation_samples,
    )
    warnings = list(evaluation.warnings)
    sparse = sum(x.samples < minimum_bin_samples for x in learned)
    if sparse:
        warnings.append(f"{sparse} calibration bins use global-rate fallback")
    if evaluation.expected_calibration_error > maximum_ece:
        warnings.append("Held-out ECE exceeds promotion threshold")
    eligible = (
        len(heldout) >= minimum_evaluation_samples
        and evaluation.expected_calibration_error <= maximum_ece
        and not any(x.samples < minimum_bin_samples for x in learned)
    )
    payload = {
        "bins": [(x.lower, x.upper, x.samples, x.observed_rate) for x in learned],
        "train": sorted(training_periods),
        "evaluation": sorted(evaluation_periods),
        "evaluation_fingerprint": evaluation.fingerprint,
    }
    fingerprint = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return CalibrationArtifact(
        tuple(learned), tuple(sorted(training_periods)),
        tuple(sorted(evaluation_periods)), len(train), evaluation,
        fingerprint, eligible, tuple(dict.fromkeys(warnings)),
    )


def apply_calibrator(score: float, artifact: CalibrationArtifact) -> float:
    if not artifact.eligible:
        raise ValueError("calibration artifact is not eligible")
    if not isfinite(score) or not 0 <= score <= 1:
        raise ValueError("invalid heuristic score")
    index = min(len(artifact.bins) - 1, int(score * len(artifact.bins)))
    return artifact.bins[index].observed_rate
