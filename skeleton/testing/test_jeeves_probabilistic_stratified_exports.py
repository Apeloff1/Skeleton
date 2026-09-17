from __future__ import annotations

import skeleton.jeeves.probabilistic as probabilistic


def test_probabilistic_facade_exports_stratified_conformal_surface() -> None:
    expected = {
        "ConformalBucketState",
        "ConformalStratumKey",
        "StratifiedConformalConfig",
        "StratifiedConformalReport",
        "StratifiedConformalStep",
        "StratifiedForecastInterval",
        "StratifiedForecastObservation",
        "conformalize_next_stratified_forecast",
        "evaluate_stratified_conformal",
        "validate_stratified_conformal_report",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_conformal_governance_surface() -> None:
    expected = {
        "ConformalGovernanceDecision",
        "ConformalGovernanceGate",
        "evaluate_conformal_governance",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)
