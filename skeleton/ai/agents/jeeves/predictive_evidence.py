"""Provenance-safe evidence bridge for Jeeves predictive results.

Predictive outputs are analysis, not facts. This bridge preserves that boundary:

* one immutable observation describes only the source-series identity/geometry;
* one factual feature repeats the source-series fingerprint as the analysis root;
* one horizon-specific hypothesis records each deterministic forward claim; and
* one calibrated prediction record is emitted per forecast horizon.

Building a bundle has no side effects. Persistence into ``LearningEvidenceStore``
is a separate explicit operation so model evaluation can never silently become
learning-state mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.historical_forecasting import HistoricalSeries
from skeleton.jeeves.historical_models import canonical_fingerprint
from skeleton.jeeves.predictive_engine import PredictiveResult
from skeleton.learning.evidence import (
    EvidenceProvenance,
    Feature,
    Hypothesis,
    LearningEvidenceError,
    LearningEvidenceStore,
    Observation,
    Prediction,
    UpdateRecord,
    empty_calibration,
)


class PredictiveEvidenceError(LearningEvidenceError):
    """Fail-closed predictive evidence bridge violation."""

    code = "JVS.PREDICTIVE_EVIDENCE"
    http_status = 422


@dataclass(frozen=True, slots=True)
class PredictiveEvidenceBundle:
    observation: Observation
    source_feature: Feature
    hypotheses: tuple[Hypothesis, ...]
    predictions: tuple[Prediction, ...]
    predictive_result_fingerprint: str
    bundle_fingerprint: str

    @property
    def hypothesis(self) -> Hypothesis:
        """Compatibility view of the first horizon-specific hypothesis."""
        if not self.hypotheses:
            raise PredictiveEvidenceError(
                "predictive evidence bundle has no hypotheses",
                context={"reason": "empty_hypotheses"},
            )
        return self.hypotheses[0]


class PredictiveEvidenceBridge:
    """Create and explicitly persist analysis evidence for one forecast result."""

    def build(
        self,
        *,
        series: HistoricalSeries,
        result: PredictiveResult,
        subject_id: str,
        observed_at: float,
        clock_version: int,
    ) -> PredictiveEvidenceBundle:
        if not isinstance(series, HistoricalSeries):
            raise PredictiveEvidenceError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        if not isinstance(result, PredictiveResult):
            raise PredictiveEvidenceError(
                "result must be PredictiveResult",
                context={"reason": "invalid_result"},
            )
        if result.training_fingerprint != series.fingerprint:
            raise PredictiveEvidenceError(
                "predictive result does not belong to supplied source series",
                context={"reason": "series_fingerprint_mismatch"},
            )
        if result.conformal_band is None:
            raise PredictiveEvidenceError(
                "calibrated uncertainty is required before prediction evidence is emitted",
                context={"reason": "uncalibrated_prediction"},
            )
        if not result.points:
            raise PredictiveEvidenceError(
                "predictive result contains no forecast points",
                context={"reason": "empty_prediction"},
            )
        horizons = tuple(point.horizon for point in result.points)
        if len(set(horizons)) != len(horizons):
            raise PredictiveEvidenceError(
                "predictive result contains duplicate horizons",
                context={"reason": "duplicate_horizon"},
            )

        root_payload = {
            "series_fingerprint": series.fingerprint,
            "point_count": len(series.observations),
            "start_timestamp": series.observations[0].timestamp,
            "end_timestamp": series.observations[-1].timestamp,
        }
        root_token = canonical_fingerprint(
            {
                "series_fingerprint": series.fingerprint,
                "subject_id": subject_id,
                "observed_at": observed_at,
                "clock_version": clock_version,
            }
        )[:24]
        root_id = f"pred-series-{root_token}"
        observation = Observation(
            observation_id=root_id,
            subject_id=subject_id,
            payload=root_payload,
            provenance=EvidenceProvenance(
                source_id=f"jeeves-predictive-series:{root_token}",
                source_kind="historical-series",
                observed_at=observed_at,
                clock_version=clock_version,
                fingerprint=canonical_fingerprint(root_payload),
            ),
        )

        feature_id = f"pred-source-{root_token}"
        feature_name = "series_fingerprint"
        feature_value = series.fingerprint
        source_feature = Feature(
            feature_id=feature_id,
            subject_id=subject_id,
            name=feature_name,
            value=feature_value,
            observation_ids=(observation.observation_id,),
            provenance=EvidenceProvenance(
                source_id=f"jeeves-predictive-source:{root_token}",
                source_kind="derived-feature",
                observed_at=observed_at,
                clock_version=clock_version,
                fingerprint=canonical_fingerprint(
                    {
                        "name": feature_name,
                        "value": feature_value,
                        "subject_id": subject_id,
                    }
                ),
                parent_ids=(observation.observation_id,),
            ),
        )

        analysis_token = canonical_fingerprint(
            {
                "fact_root": root_token,
                "predictive_result_fingerprint": result.result_fingerprint,
            }
        )[:24]
        confidence = result.conformal_band.coverage
        hypotheses: list[Hypothesis] = []
        predictions: list[Prediction] = []
        for point in result.points:
            horizon_token = f"{analysis_token[:16]}-h{point.horizon}"
            claim = (
                f"Jeeves selected predictive route {result.selected_label!r} for horizon "
                f"{point.horizon} with result fingerprint {result.result_fingerprint}."
            )
            hypothesis_id = f"pred-hyp-{horizon_token}"
            hypothesis = Hypothesis(
                hypothesis_id=hypothesis_id,
                subject_id=subject_id,
                claim=claim,
                feature_ids=(source_feature.feature_id,),
                confidence=1.0,
                provenance=EvidenceProvenance(
                    source_id=f"jeeves-predictive-decision:{horizon_token}",
                    source_kind="predictive-analysis",
                    observed_at=observed_at,
                    clock_version=clock_version,
                    fingerprint=canonical_fingerprint(
                        {
                            "claim": claim,
                            "polarity": "affirm",
                            "subject_id": subject_id,
                        }
                    ),
                    parent_ids=(source_feature.feature_id,),
                ),
            )
            channel = f"jeeves-predictive-{horizon_token}"
            prediction_id = f"pred-{horizon_token}"
            prediction = Prediction(
                prediction_id=prediction_id,
                hypothesis_id=hypothesis.hypothesis_id,
                expected=point.predicted,
                confidence=confidence,
                channel=channel,
                calibration=empty_calibration(channel, confidence),
                provenance=EvidenceProvenance(
                    source_id=f"jeeves-predictive-value:{horizon_token}",
                    source_kind="predictive-analysis",
                    observed_at=observed_at,
                    clock_version=clock_version,
                    fingerprint=canonical_fingerprint(
                        {
                            "hypothesis_id": hypothesis.hypothesis_id,
                            "expected": point.predicted,
                        }
                    ),
                    parent_ids=(hypothesis.hypothesis_id,),
                ),
            )
            hypotheses.append(hypothesis)
            predictions.append(prediction)

        hypothesis_tuple = tuple(hypotheses)
        prediction_tuple = tuple(predictions)
        payload = {
            "observation": observation.observation_id,
            "feature": source_feature.feature_id,
            "hypotheses": [item.hypothesis_id for item in hypothesis_tuple],
            "predictions": [item.prediction_id for item in prediction_tuple],
            "result": result.result_fingerprint,
            "analysis_token": analysis_token,
        }
        return PredictiveEvidenceBundle(
            observation=observation,
            source_feature=source_feature,
            hypotheses=hypothesis_tuple,
            predictions=prediction_tuple,
            predictive_result_fingerprint=result.result_fingerprint,
            bundle_fingerprint=canonical_fingerprint(payload),
        )

    def persist(
        self,
        store: LearningEvidenceStore,
        bundle: PredictiveEvidenceBundle,
    ) -> tuple[UpdateRecord, ...]:
        """Explicitly persist one bundle, reusing an identical fact root safely."""
        if not isinstance(store, LearningEvidenceStore):
            raise PredictiveEvidenceError(
                "store must be LearningEvidenceStore",
                context={"reason": "invalid_store"},
            )
        if not isinstance(bundle, PredictiveEvidenceBundle):
            raise PredictiveEvidenceError(
                "bundle must be PredictiveEvidenceBundle",
                context={"reason": "invalid_bundle"},
            )

        existing_hypothesis_ids = {item.hypothesis_id for item in store.hypotheses()}
        duplicate_hypotheses = [
            item.hypothesis_id
            for item in bundle.hypotheses
            if item.hypothesis_id in existing_hypothesis_ids
        ]
        if duplicate_hypotheses:
            raise PredictiveEvidenceError(
                "predictive hypothesis already exists",
                context={
                    "reason": "duplicate_analysis",
                    "hypothesis_id": duplicate_hypotheses[0],
                },
            )
        existing_prediction_ids = {item.prediction_id for item in store.predictions()}
        duplicate_predictions = [
            item.prediction_id
            for item in bundle.predictions
            if item.prediction_id in existing_prediction_ids
        ]
        if duplicate_predictions:
            raise PredictiveEvidenceError(
                "predictive prediction already exists",
                context={
                    "reason": "duplicate_analysis",
                    "prediction_id": duplicate_predictions[0],
                },
            )

        updates: list[UpdateRecord] = []
        observations = {item.observation_id: item for item in store.observations()}
        existing_observation = observations.get(bundle.observation.observation_id)
        if existing_observation is None:
            updates.append(store.record_observation(bundle.observation))
        elif existing_observation != bundle.observation:
            raise PredictiveEvidenceError(
                "existing series fact root conflicts with predictive bundle",
                context={"reason": "fact_root_conflict"},
            )

        features = {item.feature_id: item for item in store.features()}
        existing_feature = features.get(bundle.source_feature.feature_id)
        if existing_feature is None:
            updates.append(store.record_feature(bundle.source_feature))
        elif existing_feature != bundle.source_feature:
            raise PredictiveEvidenceError(
                "existing source feature conflicts with predictive bundle",
                context={"reason": "source_feature_conflict"},
            )

        for hypothesis in bundle.hypotheses:
            updates.append(store.record_hypothesis(hypothesis))
        for prediction in bundle.predictions:
            updates.append(store.record_prediction(prediction))
        return tuple(updates)


def summarize_predictive_evidence(bundle: PredictiveEvidenceBundle) -> dict[str, object]:
    hypothesis_ids = [item.hypothesis_id for item in bundle.hypotheses]
    return {
        "observation_id": bundle.observation.observation_id,
        "source_feature_id": bundle.source_feature.feature_id,
        "hypothesis_id": hypothesis_ids[0] if hypothesis_ids else None,
        "hypothesis_ids": hypothesis_ids,
        "prediction_ids": [item.prediction_id for item in bundle.predictions],
        "prediction_count": len(bundle.predictions),
        "predictive_result_fingerprint": bundle.predictive_result_fingerprint,
        "bundle_fingerprint": bundle.bundle_fingerprint,
    }