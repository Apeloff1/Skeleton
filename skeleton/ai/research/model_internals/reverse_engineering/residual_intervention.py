"""Causal residual-stream intervention summaries for authorized local models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ResidualInterventionObservation:
    observation_id: str
    layer_id: str
    input_digest: str
    control_output_digest: str
    intervention_output_digest: str
    metric_before: float
    metric_after: float
    intervention_kind: str

    def __post_init__(self) -> None:
        if not self.observation_id or not self.layer_id or not self.intervention_kind:
            raise ReverseEngineeringError("residual-intervention identity fields are required")
        for digest in (
            self.input_digest,
            self.control_output_digest,
            self.intervention_output_digest,
        ):
            if not is_sha256_digest(digest):
                raise ReverseEngineeringError("intervention digests must be sha256 hex digests")
        if not isfinite(self.metric_before) or not isfinite(self.metric_after):
            raise ReverseEngineeringError("intervention metrics must be finite")

    @property
    def delta(self) -> float:
        return self.metric_after - self.metric_before


@dataclass(frozen=True)
class ResidualInterventionReport:
    layer_id: str
    intervention_kind: str
    observation_count: int
    changed_output_count: int
    mean_metric_delta: float
    mean_absolute_metric_delta: float
    positive_delta_ratio: float
    negative_delta_ratio: float
    sign_consistency: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "intervention_kind": self.intervention_kind,
            "observation_count": self.observation_count,
            "changed_output_count": self.changed_output_count,
            "mean_metric_delta": self.mean_metric_delta,
            "mean_absolute_metric_delta": self.mean_absolute_metric_delta,
            "positive_delta_ratio": self.positive_delta_ratio,
            "negative_delta_ratio": self.negative_delta_ratio,
            "sign_consistency": self.sign_consistency,
            "digest": self.digest,
        }


def analyze_residual_interventions(
    observations: Sequence[ResidualInterventionObservation],
) -> tuple[ResidualInterventionReport, ...]:
    if not observations:
        raise ReverseEngineeringError("residual-intervention analysis requires observations")
    grouped: dict[tuple[str, str], list[ResidualInterventionObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation.layer_id, observation.intervention_kind), []
        ).append(observation)

    reports: list[ResidualInterventionReport] = []
    for (layer_id, kind), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.observation_id)
        deltas = [item.delta for item in ordered]
        positive = sum(1 for delta in deltas if delta > 0.0)
        negative = sum(1 for delta in deltas if delta < 0.0)
        nonzero = positive + negative
        sign_consistency = (
            max(positive, negative) / nonzero if nonzero else 1.0
        )
        payload = {
            "layer_id": layer_id,
            "intervention_kind": kind,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "input_digest": item.input_digest,
                    "control_output_digest": item.control_output_digest,
                    "intervention_output_digest": item.intervention_output_digest,
                    "metric_before": item.metric_before,
                    "metric_after": item.metric_after,
                }
                for item in ordered
            ],
        }
        reports.append(
            ResidualInterventionReport(
                layer_id=layer_id,
                intervention_kind=kind,
                observation_count=len(ordered),
                changed_output_count=sum(
                    item.control_output_digest != item.intervention_output_digest
                    for item in ordered
                ),
                mean_metric_delta=sum(deltas) / len(deltas),
                mean_absolute_metric_delta=sum(abs(delta) for delta in deltas) / len(deltas),
                positive_delta_ratio=positive / len(deltas),
                negative_delta_ratio=negative / len(deltas),
                sign_consistency=sign_consistency,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
