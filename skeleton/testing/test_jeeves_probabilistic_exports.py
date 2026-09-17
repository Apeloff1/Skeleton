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


def test_probabilistic_facade_exports_bayesian_parameter_surface() -> None:
    expected = {
        "BayesianTrendConfig",
        "BayesianTrendEvaluation",
        "BayesianTrendFit",
        "BayesianTrendFold",
        "StudentTForecast",
        "evaluate_bayesian_trend",
        "fit_bayesian_trend",
        "forecast_bayesian_trend",
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


def test_probabilistic_facade_exports_hidden_markov_regime_surface() -> None:
    expected = {
        "GaussianRegime",
        "RegimeForecast",
        "RegimeForecastComponent",
        "RegimeHMMConfig",
        "RegimeHMMFit",
        "RegimeHMMModel",
        "RegimePosteriorStep",
        "RegimePrequentialScore",
        "evaluate_regime_hmm_prequential",
        "fit_regime_hmm",
        "forecast_regime_hmm",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_paired_arena_surface() -> None:
    expected = {
        "ArenaCandidate",
        "ArenaFold",
        "ArenaMetrics",
        "HACComparison",
        "PredictiveArenaConfig",
        "PredictiveArenaDecision",
        "PredictiveArenaReport",
        "evaluate_predictive_arena",
        "newey_west_mean_test",
        "regime_forecast_crps",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_multiscale_spectral_surface() -> None:
    expected = {
        "HarmonicComponent",
        "SpectralConfig",
        "SpectralFit",
        "SpectralPeak",
        "SpectralScore",
        "SpectralTournament",
        "discover_spectral_peaks",
        "evaluate_spectral_complexities",
        "fit_spectral_model",
        "forecast_spectral",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)


def test_probabilistic_facade_exports_cross_family_arbitration_surface() -> None:
    expected = {
        "ArbitratedForecast",
        "CrossFamilyArbitrator",
        "CrossFamilyConfig",
        "CrossFamilyReport",
        "CrossFamilyStep",
        "ExpertComponent",
        "ExpertKind",
        "PredictiveDistribution",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)
