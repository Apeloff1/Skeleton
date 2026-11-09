from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.jeeves.historical_forecasting import ForecastObservation, HistoricalSeries
from skeleton.jeeves.predictive_bidirectional import (
    BidirectionalPredictiveAuditor,
    BidirectionalPredictiveError,
    BidirectionalPredictivePolicy,
)


def _series() -> HistoricalSeries:
    return HistoricalSeries(
        series_id="availability-fixture",
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(index + 1))
            for index in range(16)
        ),
    )


def _result(
    *,
    fingerprint: str,
    interval: bool,
    regime: bool,
    shifted: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        selected_objective=0.1,
        conformal_band=SimpleNamespace(base_radius=1.0) if interval else None,
        regime_report=SimpleNamespace(report_fingerprint=f"regime:{fingerprint}") if regime else None,
        regime_shift_detected=shifted,
        selected_family="baseline",
        selected_label="last_value",
        result_fingerprint=fingerprint,
    )


class _StubEngine:
    def __init__(self, forward: SimpleNamespace, reverse: SimpleNamespace) -> None:
        self.forward = forward
        self.reverse = reverse

    def evaluate(self, series: HistoricalSeries, *, horizon: int) -> SimpleNamespace:
        del horizon
        if series.series_id.endswith(":reverse-mirror"):
            return self.reverse
        return self.forward


def _auditor(
    forward: SimpleNamespace,
    reverse: SimpleNamespace,
    *,
    policy: BidirectionalPredictivePolicy | None = None,
) -> BidirectionalPredictiveAuditor:
    auditor = BidirectionalPredictiveAuditor(audit_policy=policy)
    auditor.engine = _StubEngine(forward, reverse)  # type: ignore[assignment]
    return auditor


def test_interval_availability_mismatch_fails_closed_by_default() -> None:
    auditor = _auditor(
        _result(fingerprint="forward", interval=True, regime=False),
        _result(fingerprint="reverse", interval=False, regime=False),
    )

    report = auditor.audit(_series(), horizon=2)

    assert not report.robust
    assert not report.interval_availability_agreement
    assert report.interval_radius_asymmetry is None
    assert report.reasons == ("interval_availability_disagreement",)


def test_regime_availability_mismatch_fails_closed_by_default() -> None:
    auditor = _auditor(
        _result(fingerprint="forward", interval=False, regime=True),
        _result(fingerprint="reverse", interval=False, regime=False),
    )

    report = auditor.audit(_series(), horizon=2)

    assert not report.robust
    assert not report.regime_availability_agreement
    assert not report.regime_detection_agreement
    assert report.reasons == ("regime_availability_disagreement",)


def test_explicit_availability_opt_out_is_recorded_but_does_not_veto() -> None:
    policy = BidirectionalPredictivePolicy(
        max_objective_asymmetry=1.0,
        max_interval_radius_asymmetry=1.0,
        require_interval_availability_agreement=False,
        require_regime_availability_agreement=False,
    )
    auditor = _auditor(
        _result(fingerprint="forward", interval=True, regime=True),
        _result(fingerprint="reverse", interval=False, regime=False),
        policy=policy,
    )

    report = auditor.audit(_series(), horizon=2)

    assert report.robust
    assert not report.interval_availability_agreement
    assert not report.regime_availability_agreement
    assert report.reasons == ()


def test_regime_detection_agreement_cannot_hide_missing_diagnostic() -> None:
    policy = BidirectionalPredictivePolicy(
        require_regime_availability_agreement=False,
        require_regime_detection_agreement=True,
    )
    auditor = _auditor(
        _result(fingerprint="forward", interval=False, regime=True, shifted=False),
        _result(fingerprint="reverse", interval=False, regime=False, shifted=False),
        policy=policy,
    )

    report = auditor.audit(_series(), horizon=2)

    assert not report.regime_detection_agreement
    assert report.reasons == ("regime_detection_disagreement",)
    assert not report.robust


def test_policy_rejects_non_boolean_availability_flags() -> None:
    with pytest.raises(BidirectionalPredictiveError) as interval_exc:
        BidirectionalPredictivePolicy(  # type: ignore[arg-type]
            require_interval_availability_agreement=1,
        )
    assert interval_exc.value.context["reason"] == "invalid_policy_flag"
    assert interval_exc.value.context["field"] == "require_interval_availability_agreement"

    with pytest.raises(BidirectionalPredictiveError) as regime_exc:
        BidirectionalPredictivePolicy(  # type: ignore[arg-type]
            require_regime_availability_agreement="yes",
        )
    assert regime_exc.value.context["reason"] == "invalid_policy_flag"
    assert regime_exc.value.context["field"] == "require_regime_availability_agreement"
