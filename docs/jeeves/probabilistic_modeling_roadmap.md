# Jeeves Predictive Modeling Roadmap

This roadmap records the next mathematical layers after the initial probabilistic
state-space stack. It is intentionally evidence-gated: each layer must earn trust
through out-of-sample performance and calibration before it becomes eligible for
runtime routing.

## Layer 1 — structural probability models

Status: implemented in the probabilistic state-space tranche.

- local level
- local linear trend
- robust local linear trend
- posterior covariance propagation
- multi-step Gaussian predictive distributions
- proper log-score family tournament

## Layer 2 — dynamic Bayesian arbitration

Status: implemented in the probabilistic state-space tranche.

- prequential Bayesian model averaging
- forgetting factor for non-stationarity
- model-weight floor
- Gaussian mixture uncertainty
- exact mixture CRPS
- posterior entropy/effective model count

## Layer 3 — calibration and honesty

Status: implemented in the probabilistic state-space tranche.

- PIT diagnostics
- exact mixture CDF evaluation
- deterministic mixture-quantile inversion
- 50/80/90/95 central coverage
- interval sharpness
- pinball loss
- calibration CUSUM

## Layer 4 — regime-switching latent dynamics

Next candidate.

- Hamilton-filter hidden Markov state probabilities
- transition-matrix regularization
- heavy-tailed emission option
- regime-conditional state-space parameters
- posterior regime entropy
- regime-duration diagnostics
- label-switching-resistant deterministic ordering

Promotion gates:

- improve prequential log score against the best single-regime structural model;
- no material CRPS regression;
- stable regime posterior under endpoint perturbation;
- no future-target leakage in state inference;
- fail closed when state occupancy becomes too thin.

## Layer 5 — Bayesian parameter uncertainty

Next candidate.

- conjugate normal/inverse-gamma local regression blocks where possible
- transparent Laplace approximation for non-conjugate parameters
- posterior predictive variance decomposed into observation, state, parameter,
  and model uncertainty
- effective sample size and posterior concentration diagnostics

Promotion gates:

- parameter uncertainty must improve coverage calibration without destroying
  sharpness;
- posterior intervals must contract with informative repeated evidence;
- priors must be explicit and versioned.

## Layer 6 — conformalized distributional forecasting

Next candidate.

- rolling conformal residual correction
- adaptive conformal coverage controller
- weighted conformal scores under detected distribution shift
- conformalized mixture quantiles
- multi-horizon simultaneous coverage controls

Promotion gates:

- empirical coverage inside configured tolerance on forward holdout;
- interval-width budget against uncorrected probabilistic forecasts;
- calibration data strictly precedes the target being covered.

## Layer 7 — cross-series dependency models

Future candidate after scalar custody is proven.

- shrinkage covariance estimation
- dynamic factor models
- low-rank latent factors
- robust covariance under outliers
- graph-structured conditional dependencies
- lead/lag analysis guarded against multiple-testing artifacts

Promotion gates:

- deterministic feature universe and timestamps;
- no target-derived contemporaneous leakage;
- comparison against independent univariate forecasts;
- explicit false-discovery controls for large dependency searches.

## Layer 8 — causal and counterfactual research plane

Research-only until separately governed.

- intervention-aware structural causal graphs
- synthetic controls
- difference-in-differences diagnostics
- invariant prediction checks
- sensitivity to unobserved confounding

Causal outputs must never be inferred from predictive accuracy alone. They require
assumptions, provenance, identification checks, and explicit uncertainty.

## Layer 9 — decision layer with abstention

Future governed integration.

- utility functions separated from predictive probability
- risk constraints and abstention thresholds
- uncertainty-aware action eligibility
- scenario stress testing
- expected-value decomposition
- rollback on calibration or evidence regression

The predictive stack must remain useful even when no action is permitted. A model
being mathematically interesting is not itself an authorization to act.
