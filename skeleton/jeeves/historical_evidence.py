"""Provenance-ready evidence bridge for Jeeves historical reports.

This bridge is intentionally *construction only*. It creates an immutable root
observation describing the supplied historical series and feature records
containing derived evaluation measurements. It never receives or mutates a
``LearningEvidenceStore`` and therefore cannot silently promote a model or
self-update Jeeves.

The root observation stays factual: label, sample count, endpoint values,
timestamp presence, and deterministic content fingerprints. Evaluation output,
including uncertainty calibration, remains on the derived ``Feature`` plane.
Callers that want persistence must explicitly record the returned objects in an
evidence store. Evidence construction also requires an explicit observation time;
there is no fixture-time default that can silently become stale at persistence.
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
from .historical_uncertainty import HistoricalUncertaintyReport


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceBundle:
    """Fact root plus derived historical measurements ready for explicit storage."""

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
    observed_at: float | None = None,
    clock_version: int = 1,
    source_id: str = "jeeves-historical-lab",
    source_kind: str = "historical-evaluation",
    uri: str | None = None,
) -> HistoricalEvidenceBundle:
    """Construct factual/feature evidence without mutating any evidence store.

    ``observed_at`` is intentionally required at runtime. Historical evidence may
    be persisted into freshness-enforcing stores, so inventing a fixture timestamp
    here would produce deterministically stale evidence in real deployments.
    """

    observed_at = _require_observed_at(observed_at)
    _require_report_series_alignment(report, series)
    series_fingerprint = _series_fingerprint(series)
    report_fingerprint = report.fingerprint

    # The root fact identity depends only on the supplied series. Analysis
    # configuration/report identity belongs on the derived feature plane.
    observation_id = f"histobs-{series_fingerprint[:32]}"
    observation_payload: dict[str, object] = {
        "series_label": series.label,
        "sample_count": len(series.values),
        "first_value": series.values[0],
        "last_value": series.values[-1],
        "has_timestamps": series.timestamps is not None,
        "series_fingerprint": series_fingerprint,
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


def build_uncertainty_evidence(
    report: HistoricalUncertaintyReport,
    series: HistoricalSeries,
    *,
    subject_id: str,
    observed_at: float | None = None,
    clock_version: int = 1,
    source_id: str = "jeeves-historical-lab",
    source_kind: str = "historical-evaluation",
    uri: str | None = None,
) -> HistoricalEvidenceBundle:
    """Extend calibrated evidence with conformal uncertainty measurements.

    The same series-only observation is reused. Uncertainty diagnostics are
    additional derived features and cannot alter factual identity. ``observed_at``
    must be supplied explicitly for the same freshness reason as base evidence.
    """

    observed_at = _require_observed_at(observed_at)
    base = build_historical_evidence(
        report.robustness.full,
        series,
        subject_id=subject_id,
        observed_at=observed_at,
        clock_version=clock_version,
        source_id=source_id,
        source_kind=source_kind,
        uri=uri,
    )
    uncertainty_values = _uncertainty_feature_values(report)
    extras = tuple(
        _make_feature(
            index=len(base.features) + index,
            name=name,
            value=value,
            subject_id=subject_id,
            observation_id=base.observation.observation_id,
            report_fingerprint=report.fingerprint,
            source_id=source_id,
            source_kind=source_kind,
            observed_at=observed_at,
            clock_version=clock_version,
            uri=uri,
        )
        for index, (name, value) in enumerate(uncertainty_values.items(), start=1)
    )
    return HistoricalEvidenceBundle(
        observation=base.observation,
        features=base.features + extras,
        report_fingerprint=report.fingerprint,
        series_fingerprint=base.series_fingerprint,
    )


def _feature_values(report: CalibratedBidirectionalReport) -> dict[str, object]:
    payload = report.as_payload()
    candidate = report.decision.candidate_diagnostics
    return {
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


def _uncertainty_feature_values(report: HistoricalUncertaintyReport) -> dict[str, object]:
    payload = report.as_payload()
    return {
        "uncertainty_selected_mode": payload["selected_mode"],
        "uncertainty_accepted": payload["uncertainty_accepted"],
        "uncertainty_robustness_accepted": payload["robustness_accepted"],
        "uncertainty_nominal_coverage": payload["nominal_coverage"],
        "uncertainty_forward_coverage": payload["forward_coverage"],
        "uncertainty_backward_coverage": payload["backward_coverage"],
        "uncertainty_coverage_gap": payload["coverage_gap"],
        "uncertainty_forward_average_width": payload["forward_average_width"],
        "uncertainty_backward_average_width": payload["backward_average_width"],
        "uncertainty_width_asymmetry": payload["width_asymmetry"],
        "uncertainty_forward_calibrated_folds": report.forward.calibrated_folds,
        "uncertainty_backward_calibrated_folds": report.backward.calibrated_folds,
        "uncertainty_fingerprint": report.fingerprint,
        "robustness_fingerprint": report.robustness.fingerprint,
    }


def _require_observed_at(observed_at: float | None) -> float:
    if observed_at is None:
        raise LearningEvidenceError(
            "historical evidence requires an explicit observation timestamp",
            context={"reason": "missing_observed_at", "field": "observed_at"},
        )
    return observed_at


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
    return canonical_fingerprint(
        {
            "label": series.label,
            "values": series.values,
            "timestamps": series.timestamps,
        }
    )


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
