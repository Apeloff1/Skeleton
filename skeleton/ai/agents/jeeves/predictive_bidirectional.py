"""Bidirectional temporal stress testing for Jeeves predictive modeling.

Forecasting is intrinsically directional, so reverse-time agreement is *not* a
universal correctness requirement.  It is nevertheless a useful falsification
surface: the exact same model-selection machinery can be replayed on a mirrored
history to expose severe directional instability, hidden dependence on endpoint
geometry, or an unexpectedly brittle family choice.

This module therefore treats reverse-time evaluation as an explicit diagnostic.
Deployments may opt into strict family/regime agreement, while evidence-plane
availability agreement is fail-closed by default. Reverse forecasts are never
used as production predictions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_forecasting import (
    ForecastObservation,
    HistoricalForecastError,
    HistoricalSeries,
)
from skeleton.jeeves.historical_models import canonical_fingerprint
from skeleton.jeeves.predictive_engine import (
    JeevesPredictiveEngine,
    PredictiveEnginePolicy,
    PredictiveResult,
)


_EPSILON: Final = 1e-12


class BidirectionalPredictiveError(HistoricalForecastError):
    """Fail-closed bidirectional predictive audit contract violation."""

    code = "JVS.PREDICTIVE_BIDIRECTIONAL"
    http_status = 422


@dataclass(frozen=True, slots=True)
class BidirectionalPredictivePolicy:
    max_objective_asymmetry: float = 0.35
    max_interval_radius_asymmetry: float = 0.60
    require_interval_availability_agreement: bool = True
    require_regime_availability_agreement: bool = True
    require_family_agreement: bool = False
    require_regime_detection_agreement: bool = False

    def __post_init__(self) -> None:
        objective = _non_negative("max_objective_asymmetry", self.max_objective_asymmetry)
        radius = _non_negative("max_interval_radius_asymmetry", self.max_interval_radius_asymmetry)
        if objective > 10.0 or radius > 10.0:
            raise BidirectionalPredictiveError(
                "asymmetry thresholds must not exceed 10",
                context={"reason": "threshold_too_large"},
            )
        for name in (
            "require_interval_availability_agreement",
            "require_regime_availability_agreement",
            "require_family_agreement",
            "require_regime_detection_agreement",
        ):
            if not isinstance(getattr(self, name), bool):
                raise BidirectionalPredictiveError(
                    f"{name} must be boolean",
                    context={"reason": "invalid_policy_flag", "field": name},
                )
        object.__setattr__(self, "max_objective_asymmetry", objective)
        object.__setattr__(self, "max_interval_radius_asymmetry", radius)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "max_objective_asymmetry": self.max_objective_asymmetry,
                "max_interval_radius_asymmetry": self.max_interval_radius_asymmetry,
                "require_interval_availability_agreement": self.require_interval_availability_agreement,
                "require_regime_availability_agreement": self.require_regime_availability_agreement,
                "require_family_agreement": self.require_family_agreement,
                "require_regime_detection_agreement": self.require_regime_detection_agreement,
            }
        )


@dataclass(frozen=True, slots=True)
class BidirectionalPredictiveReport:
    forward: PredictiveResult
    reverse: PredictiveResult
    objective_asymmetry: float
    interval_radius_asymmetry: float | None
    interval_availability_agreement: bool
    regime_availability_agreement: bool
    family_agreement: bool
    regime_detection_agreement: bool
    robust: bool
    reasons: tuple[str, ...]
    mirrored_series_fingerprint: str
    policy_fingerprint: str
    report_fingerprint: str


class BidirectionalPredictiveAuditor:
    """Replay one predictive policy forward and on an exact reverse-time mirror."""

    def __init__(
        self,
        *,
        engine_policy: PredictiveEnginePolicy | None = None,
        audit_policy: BidirectionalPredictivePolicy | None = None,
    ) -> None:
        self.engine_policy = engine_policy or PredictiveEnginePolicy()
        self.audit_policy = audit_policy or BidirectionalPredictivePolicy()
        if not isinstance(self.engine_policy, PredictiveEnginePolicy):
            raise BidirectionalPredictiveError(
                "engine_policy must be PredictiveEnginePolicy",
                context={"reason": "invalid_engine_policy"},
            )
        if not isinstance(self.audit_policy, BidirectionalPredictivePolicy):
            raise BidirectionalPredictiveError(
                "audit_policy must be BidirectionalPredictivePolicy",
                context={"reason": "invalid_audit_policy"},
            )
        self.engine = JeevesPredictiveEngine(self.engine_policy)

    def audit(self, series: HistoricalSeries, *, horizon: int) -> BidirectionalPredictiveReport:
        if not isinstance(series, HistoricalSeries):
            raise BidirectionalPredictiveError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        mirrored = mirror_series(series)
        forward = self.engine.evaluate(series, horizon=horizon)
        reverse = self.engine.evaluate(mirrored, horizon=horizon)

        objective_asymmetry = _relative_asymmetry(
            forward.selected_objective,
            reverse.selected_objective,
        )
        interval_asymmetry = _interval_asymmetry(forward, reverse)
        interval_availability_agreement = (
            (forward.conformal_band is None) == (reverse.conformal_band is None)
        )
        regime_availability_agreement = (
            (forward.regime_report is None) == (reverse.regime_report is None)
        )
        family_agreement = forward.selected_family == reverse.selected_family
        regime_agreement = (
            regime_availability_agreement
            and forward.regime_shift_detected == reverse.regime_shift_detected
        )

        reasons: list[str] = []
        if objective_asymmetry > self.audit_policy.max_objective_asymmetry + _EPSILON:
            reasons.append("objective_asymmetry")
        if (
            self.audit_policy.require_interval_availability_agreement
            and not interval_availability_agreement
        ):
            reasons.append("interval_availability_disagreement")
        if (
            interval_asymmetry is not None
            and interval_asymmetry > self.audit_policy.max_interval_radius_asymmetry + _EPSILON
        ):
            reasons.append("interval_radius_asymmetry")
        if (
            self.audit_policy.require_regime_availability_agreement
            and not regime_availability_agreement
        ):
            reasons.append("regime_availability_disagreement")
        if self.audit_policy.require_family_agreement and not family_agreement:
            reasons.append("family_disagreement")
        if self.audit_policy.require_regime_detection_agreement and not regime_agreement:
            reasons.append("regime_detection_disagreement")

        robust = not reasons
        payload = {
            "series": series.fingerprint,
            "mirrored_series": mirrored.fingerprint,
            "engine_policy": self.engine_policy.fingerprint,
            "audit_policy": self.audit_policy.fingerprint,
            "forward": forward.result_fingerprint,
            "reverse": reverse.result_fingerprint,
            "objective_asymmetry": objective_asymmetry,
            "interval_radius_asymmetry": interval_asymmetry,
            "interval_availability_agreement": interval_availability_agreement,
            "regime_availability_agreement": regime_availability_agreement,
            "family_agreement": family_agreement,
            "regime_detection_agreement": regime_agreement,
            "robust": robust,
            "reasons": reasons,
        }
        return BidirectionalPredictiveReport(
            forward=forward,
            reverse=reverse,
            objective_asymmetry=objective_asymmetry,
            interval_radius_asymmetry=interval_asymmetry,
            interval_availability_agreement=interval_availability_agreement,
            regime_availability_agreement=regime_availability_agreement,
            family_agreement=family_agreement,
            regime_detection_agreement=regime_agreement,
            robust=robust,
            reasons=tuple(reasons),
            mirrored_series_fingerprint=mirrored.fingerprint,
            policy_fingerprint=self.audit_policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )


def mirror_series(series: HistoricalSeries) -> HistoricalSeries:
    """Return an exact involutive reverse-time mirror with increasing timestamps.

    For original timestamps ``t[i]`` on ``[t0, tn]``, mirrored timestamp ``i`` is
    ``t0 + tn - t[n-i]``. Applying this transformation twice restores both the
    original values and timestamp geometry exactly (subject only to ordinary
    floating-point representation of the original inputs).
    """
    if not isinstance(series, HistoricalSeries):
        raise BidirectionalPredictiveError(
            "series must be HistoricalSeries",
            context={"reason": "invalid_series"},
        )
    observations = series.observations
    first = observations[0].timestamp
    last = observations[-1].timestamp
    mirrored = tuple(
        ForecastObservation(
            timestamp=first + last - source.timestamp,
            value=source.value,
        )
        for source in reversed(observations)
    )
    return HistoricalSeries(
        series_id=_mirrored_id(series.series_id),
        observations=mirrored,
    )


def summarize_bidirectional_predictive(report: BidirectionalPredictiveReport) -> dict[str, object]:
    return {
        "robust": report.robust,
        "reasons": list(report.reasons),
        "objective_asymmetry": report.objective_asymmetry,
        "interval_radius_asymmetry": report.interval_radius_asymmetry,
        "interval_availability_agreement": report.interval_availability_agreement,
        "regime_availability_agreement": report.regime_availability_agreement,
        "family_agreement": report.family_agreement,
        "regime_detection_agreement": report.regime_detection_agreement,
        "forward_family": report.forward.selected_family,
        "reverse_family": report.reverse.selected_family,
        "forward_label": report.forward.selected_label,
        "reverse_label": report.reverse.selected_label,
        "forward_objective": report.forward.selected_objective,
        "reverse_objective": report.reverse.selected_objective,
        "mirrored_series_fingerprint": report.mirrored_series_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }


def _mirrored_id(series_id: str) -> str:
    suffix = ":reverse-mirror"
    if series_id.endswith(suffix):
        return series_id[: -len(suffix)]
    return f"{series_id}{suffix}"


def _relative_asymmetry(left: float, right: float) -> float:
    left = _finite("left_objective", left)
    right = _finite("right_objective", right)
    denominator = max(abs(left), abs(right), _EPSILON)
    return abs(left - right) / denominator


def _interval_asymmetry(left: PredictiveResult, right: PredictiveResult) -> float | None:
    if left.conformal_band is None or right.conformal_band is None:
        return None
    return _relative_asymmetry(
        left.conformal_band.base_radius,
        right.conformal_band.base_radius,
    )


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BidirectionalPredictiveError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise BidirectionalPredictiveError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _non_negative(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise BidirectionalPredictiveError(
            f"{name} must be non-negative",
            context={"reason": "negative_threshold", "field": name},
        )
    return number