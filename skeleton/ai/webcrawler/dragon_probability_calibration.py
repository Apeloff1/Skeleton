"""Deterministic, conservative probabilistic calibration and drift reports.

Uses labelled held-out outcomes to evaluate probability quality. Never
changes source beliefs automatically or claims calibration without labels.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, log
from hashlib import sha256
import json


@dataclass(frozen=True)
class CalibrationExample:
    claim_id: str
    predicted_probability: float
    observed_truth: bool
    source_group: str
    period: str


@dataclass(frozen=True)
class CalibrationReport:
    samples: int
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    group_scores: tuple[tuple[str, int, float], ...]
    fingerprint: str
    warnings: tuple[str, ...]


def calibration_report(examples: tuple[CalibrationExample, ...], *,
                       authorized: bool, bins: int = 10,
                       minimum_samples: int = 30) -> CalibrationReport:
    if not authorized:
        raise PermissionError("calibration requires authorization")
    if not 2 <= bins <= 100 or not 1 <= minimum_samples <= 100000:
        raise ValueError("invalid calibration configuration")
    if len(examples) > 1000000:
        raise ValueError("calibration sample budget exceeded")
    seen = set()
    grouped: dict[str, list[CalibrationExample]] = {}
    buckets: list[list[CalibrationExample]] = [[] for _ in range(bins)]
    for example in examples:
        for value, label in (
            (example.claim_id, "claim id"),
            (example.source_group, "source group"),
            (example.period, "evaluation period"),
        ):
            if not isinstance(value, str) or not 1 <= len(value) <= 256:
                raise ValueError(f"invalid {label}")
        if not isinstance(example.observed_truth, bool):
            raise ValueError("ground truth must be boolean")
        probability = example.predicted_probability
        if not isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("invalid predicted probability")
        identity = (example.claim_id, example.source_group, example.period)
        if identity in seen:
            raise ValueError("duplicate calibration identity")
        seen.add(identity)
        grouped.setdefault(example.source_group, []).append(example)
        buckets[min(bins - 1, int(probability * bins))].append(example)
    if not examples:
        raise ValueError("calibration requires labelled examples")
    brier = sum(
        (x.predicted_probability - int(x.observed_truth)) ** 2
        for x in examples
    ) / len(examples)
    epsilon = 1e-12
    logloss = -sum(
        int(x.observed_truth) * log(max(epsilon, x.predicted_probability))
        + (1 - int(x.observed_truth)) * log(
            max(epsilon, 1 - x.predicted_probability)
        )
        for x in examples
    ) / len(examples)
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        observed = sum(int(x.observed_truth) for x in bucket) / len(bucket)
        predicted = sum(x.predicted_probability for x in bucket) / len(bucket)
        ece += len(bucket) / len(examples) * abs(predicted - observed)
    group_scores = tuple(sorted(
        (group, len(rows), round(sum(
            (x.predicted_probability - int(x.observed_truth)) ** 2
            for x in rows
        ) / len(rows), 8))
        for group, rows in grouped.items()
    ))
    warnings = []
    if len(examples) < minimum_samples:
        warnings.append("Insufficient labelled data for robust calibration")
    if any(count < minimum_samples for _, count, _ in group_scores):
        warnings.append("One or more source groups are under-sampled")
    if ece > 0.1:
        warnings.append("Predicted probabilities are poorly calibrated")
    fingerprint = sha256(json.dumps(sorted(
        (x.claim_id, x.predicted_probability, x.observed_truth,
         x.source_group, x.period)
        for x in examples
    ), separators=(",", ":")).encode()).hexdigest()
    return CalibrationReport(
        len(examples), round(brier, 8), round(logloss, 8),
        round(ece, 8), group_scores, fingerprint, tuple(warnings),
    )
