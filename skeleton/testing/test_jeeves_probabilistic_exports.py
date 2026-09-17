from __future__ import annotations

import skeleton.jeeves.probabilistic as probabilistic


def test_probabilistic_facade_exports_core_state_space_surface() -> None:
    expected = {
        "GaussianForecast",
        "InnovationRegime",
        "RegimePosterior",
        "StateSpaceConfig",
        "StateSpaceError",
        "StateSpaceFamily",
        "StateSpaceFit",
        "StateSpaceScore",
        "StateSpaceTournament",
        "evaluate_state_space_families",
        "fit_state_space",
        "forecast_state_space",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_bayesian_ensemble_surface() -> None:
    expected = {
        "BayesianEnsembleConfig",
        "BayesianEnsembleReport",
        "EnsembleStep",
        "MixtureForecast",
        "OnlineBayesianEnsemble",
        "WeightedForecast",
        "gaussian_mixture_crps",
        "probability_integral_transform",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_calibration_surface() -> None:
    expected = {
        "CalibrationConfig",
        "CalibrationReport",
        "CoverageDiagnostic",
        "DistributionObservation",
        "DriftEvent",
        "PitDiagnostic",
        "calibrate_distributions",
        "central_interval",
        "mixture_cdf",
        "mixture_quantile",
        "pinball_loss",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_promotion_contracts() -> None:
    expected = {
        "ProbabilisticPromotionDecision",
        "ProbabilisticPromotionGate",
        "evaluate_probabilistic_promotion",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)
