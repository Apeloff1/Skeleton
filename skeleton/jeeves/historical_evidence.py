"""Provenance-ready evidence bridge for calibrated Jeeves historical reports.

This bridge is intentionally *construction only*.  It creates an immutable root
observation describing the supplied historical series and feature records
containing calibrated bidirectional evaluation measurements.  It never receives
or mutates a ``LearningEvidenceStore`` and therefore cannot silently promote a
model or self-update Jeeves.

The root observation stays factual: label, sample count, endpoint values,
timestamp presence, and deterministic content fingerprints.  Evaluation output
is represented as derived ``Feature`` records grounded in that observation.
Callers that want persistence must explicitly record the returned objects in an
evidence store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from skeleton.learning.evidence import (
    Feature,
    LearningEvidenceError,
    Observation,
    canonical_fingerprint,
    make_provenance,
)

from .bidirectional_calibration import CalibratedBidirectionalReport
from .historical_modes import HistoricalModeError, HistoricalSeries


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceBundle:
    """Fact root plus derived calibrated measurements ready for explicit storage."""

    observation: Observation
    features: tuple[Feature, ...]
    report_fingerprint: str
    series_fingerprint: str

    def feature_by_name(self, name: str) -> Feature:
        for feature in self.features:
            if feature.name == name:
                return feature
        raise LearningEvidenceError(
            "historical evidence feature is absent",
            context={"reason": "unknown_record", "feature_name": name},
        )


def build_historical_evidence(
    report: CalibratedBidirectionalReport,
    series: HistoricalSeries,
    *,
    subject_id: str,
    observed_at: float = 1_000.0,
    clock_version: int = 1,
    source_id: str = "jeeves-historical-lab",
    source_kind: str = "historical-evaluation",
    uri: str | None = None,
) -> HistoricalEvidenceBundle:
    """Construct factual/feature evidence without mutating any evidence store.

    The report and series labels are checked in both temporal orientations so a
    report cannot accidentally be attached to a differently named fixture.  A
    deterministic series fingerprint binds the returned fact root to the exact
    values and timestamps supplied by the caller.
    """

    _require_report_series_alignment(report, series)
    series_fingerprint = _series_fingerprint(series)
    report_fingerprint = report.fingerprint
    observation_id = f"histobs-{series_fingerprint[:20]}-{report_fingerprint[:12]}"

    observation_payload: dict[str, object] = {
        "series_label": series.label,
        "sample_count": len(series.values),
        "first_value": series.values[0],
        "last_value": series.values[-1],
        "has_timestamps": series.timestamps is not None,
        "series_fingerprint": series_fingerprint,
        "report_fingerprint": report_fingerprint,
    }
    if series.timestamps is not None:
        observation_payload["first_timestamp"] = series.timestamps[0]
        observation_payload["last_timestamp"] = series.timestamps[-1]
        observation_payload["timestamp_fingerprint"] = canonical_fingerprint(
            {"timestamps": series.timestamps}
        )

    observation = Observation(
        observation_id=observation_id,
        subject_id=subject_id,
        payload=observation_payload,
        provenance=make_provenance(
            observation_payload,
            source_id=source_id,
            source_kind=source_kind,
            observed_at=observed_at,
            clock_version=clock_version,
            uri=uri,
        ),
    )

    feature_values = _feature_values(report)
    features = tuple(
        _make_feature(
            index=index,
            name=name,
            value=value,
            subject_id=subject_id,
            observation_id=observation_id,
            report_fingerprint=report_fingerprint,
            source_id=source_id,
            source_kind=source_kind,
            observed_at=observed_at,
            clock_version=clock_version,
            uri=uri,
        )
        for index, (name, value) in enumerate(feature_values.items(), start=1)
    )
    return HistoricalEvidenceBundle(
        observation=observation,
        features=features,
        report_fingerprint=report_fingerprint,
        series_fingerprint=series_fingerprint,
    )


def _feature_values(report: CalibratedBidirectionalReport) -> dict[str, object]:
    payload = report.as_payload()
    candidate = report.decision.candidate_diagnostics
    values: dict[str, object] = {
        "selected_mode": payload["selected_mode"],
        "calibration_accepted": payload["calibration_accepted"],
        "base_bidirectional_accepted": payload["base_bidirectional_accepted"],
        "rank_correlation": payload["rank_correlation"],
        "top_k_overlap": payload["top_k_overlap"],
        "candidate_rank_gap": payload["candidate_rank_gap"],
        "candidate_p90_error_asymmetry": payload["candidate_p90_error_asymmetry"],
        "candidate_paired_targets": payload["candidate_paired_targets"],
        "candidate_paired_error_asymmetry": payload[
            "candidate_paired_error_asymmetry"
        ],
        "candidate_forward_mae": candidate.forward_mae,
        "candidate_backward_mae": candidate.backward_mae,
        "candidate_mae_asymmetry": candidate.mae_asymmetry,
        "candidate_median_error_asymmetry": candidate.median_error_asymmetry,
        "candidate_bias_ratio_asymmetry": candidate.bias_ratio_asymmetry,
        "candidate_directional_accuracy_gap": candidate.directional_accuracy_gap,
        "candidate_paired_error_correlation": candidate.paired_absolute_error_correlation,
        "calibration_fingerprint": report.fingerprint,
        "bidirectional_fingerprint": report.base.fingerprint,
        "forward_evaluation_fingerprint": report.base.forward.report.fingerprint,
        "backward_evaluation_fingerprint": report.base.backward.report.fingerprint,
    }
    return values


def _make_feature(
    *,
    index: int,
    name: str,
    value: object,
    subject_id: str,
    observation_id: str,
    report_fingerprint: str,
    source_id: str,
    source_kind: str,
    observed_at: float,
    clock_version: int,
    uri: str | None,
) -> Feature:
    feature_id = f"histfeat-{index:02d}-{name[:52]}-{report_fingerprint[:10]}"
    fingerprint_payload = {"name": name, "value": value, "subject_id": subject_id}
    return Feature(
        feature_id=feature_id,
        subject_id=subject_id,
        name=name,
        value=value,
        observation_ids=(observation_id,),
        provenance=make_provenance(
            fingerprint_payload,
            source_id=source_id,
            source_kind=source_kind,
            observed_at=observed_at,
            clock_version=clock_version,
            parent_ids=(observation_id,),
            uri=uri,
        ),
    )


def _series_fingerprint(series: HistoricalSeries) -> str:
    payload = {
        "label": series.label,
        "values": series.values,
        "timestamps": series.timestamps,
    }
    # canonical_fingerprint is already the evidence subsystem's custody hash.
    return canonical_fingerprint(payload)


def _require_report_series_alignment(
    report: CalibratedBidirectionalReport,
    series: HistoricalSeries,
) -> None:
    forward_label = report.base.forward.report.series_label
    backward_label = report.base.backward.report.series_label
    expected_backward = f"{series.label}::backward"
    if forward_label != series.label or backward_label != expected_backward:
        raise HistoricalModeError(
            "calibrated report labels do not match supplied historical series",
            context={
                "reason": "report_series_mismatch",
                "series_label": series.label,
                "forward_label": forward_label,
                "backward_label": backward_label,
            },
        )


def bundle_manifest(bundle: HistoricalEvidenceBundle) -> str:
    """Deterministic scalar manifest for logs/artifacts; contains no raw series."""

    payload: Mapping[str, object] = {
        "observation_id": bundle.observation.observation_id,
        "feature_count": len(bundle.features),
        "report_fingerprint": bundle.report_fingerprint,
        "series_fingerprint": bundle.series_fingerprint,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
