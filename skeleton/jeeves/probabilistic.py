"""Stable Jeeves probabilistic-modeling facade.

This module keeps the public import surface compact while the implementation is
split into state-space filtering, online Bayesian ensembles, distributional
calibration diagnostics, and explicit promotion eligibility contracts.
"""

from .probabilistic_calibration import (
    CalibrationConfig,
    CalibrationReport,
    CoverageDiagnostic,
    DistributionObservation,
    DriftEvent,
    PitDiagnostic,
    calibrate_distributions,
    central_interval,
    gaussian_as_mixture,
    mixture_cdf,
    mixture_quantile,
    pinball_loss,
)
from .probabilistic_contracts import (
    ProbabilisticPromotionDecision,
    ProbabilisticPromotionGate,
    evaluate_probabilistic_promotion,
)
from .probabilistic_ensemble import (
    BayesianEnsembleConfig,
    BayesianEnsembleReport,
    EnsembleStep,
    MixtureForecast,
    OnlineBayesianEnsemble,
    WeightedForecast,
    gaussian_mixture_crps,
    probability_integral_transform,
)
from .probabilistic_state_space import (
    FilterStep,
    GaussianForecast,
    InnovationRegime,
    RegimePosterior,
    SeriesValues,
    StateSpaceConfig,
    StateSpaceError,
    StateSpaceFamily,
    StateSpaceFit,
    StateSpaceScore,
    StateSpaceTournament,
    evaluate_state_space_families,
    fit_state_space,
    forecast_state_space,
)

__all__ = [
    "BayesianEnsembleConfig",
    "BayesianEnsembleReport",
    "CalibrationConfig",
    "CalibrationReport",
    "CoverageDiagnostic",
    "DistributionObservation",
    "DriftEvent",
    "EnsembleStep",
    "FilterStep",
    "GaussianForecast",
    "InnovationRegime",
    "MixtureForecast",
    "OnlineBayesianEnsemble",
    "PitDiagnostic",
    "ProbabilisticPromotionDecision",
    "ProbabilisticPromotionGate",
    "RegimePosterior",
    "SeriesValues",
    "StateSpaceConfig",
    "StateSpaceError",
    "StateSpaceFamily",
    "StateSpaceFit",
    "StateSpaceScore",
    "StateSpaceTournament",
    "WeightedForecast",
    "calibrate_distributions",
    "central_interval",
    "evaluate_probabilistic_promotion",
    "evaluate_state_space_families",
    "fit_state_space",
    "forecast_state_space",
    "gaussian_as_mixture",
    "gaussian_mixture_crps",
    "mixture_cdf",
    "mixture_quantile",
    "pinball_loss",
    "probability_integral_transform",
]
