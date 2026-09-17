from __future__ import annotations

import skeleton.jeeves.probabilistic as probabilistic


def test_probabilistic_facade_exports_regime_aware_multihorizon_surface() -> None:
    expected = {
        "HorizonConformalGovernanceEvidence",
        "HorizonStratifiedCalibration",
        "HorizonStratifiedInterval",
        "MultiHorizonConformalGovernanceEvidence",
        "MultiHorizonStratifiedCalibration",
        "MultiHorizonStratifiedIntervalLadder",
        "conformalize_multihorizon_ladder_stratified",
        "evaluate_multihorizon_conformal_governance",
        "evaluate_multihorizon_stratified_conformal",
        "validate_multihorizon_stratified_calibration",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)
