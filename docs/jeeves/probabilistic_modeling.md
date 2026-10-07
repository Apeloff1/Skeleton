# Jeeves Probabilistic Modeling

Jeeves' predictive stack treats a forecast as a distribution, not a single number.
The current probabilistic layer is offline, deterministic, provider-neutral, and
strictly separated from order execution or other autonomous actions.

## Architecture

The stack is organized into three mathematical layers:

1. `probabilistic_state_space.py`
   - local-level and local-linear-trend structural models
   - robust innovation clipping for shock resistance
   - explicit posterior covariance
   - multi-step predictive means and variances
   - soft innovation-regime posterior
   - leakage-safe expanding-window family tournament

2. `probabilistic_ensemble.py`
   - online Bayesian model averaging
   - log-space posterior weight updates
   - bounded forgetting for non-stationarity
   - non-zero model-weight floor to avoid irreversible collapse
   - finite Gaussian-mixture predictive distributions
   - exact Gaussian-mixture log score and CRPS
   - PIT output for calibration diagnostics

3. `probabilistic_calibration.py`
   - Gaussian-mixture CDF and deterministic quantile inversion
   - equal-tail predictive intervals
   - PIT histogram and Kolmogorov-Smirnov distance
   - empirical interval coverage and sharpness
   - quantile/pinball loss
   - sequential CUSUM-style calibration drift detection

A compact import surface is exposed from `skeleton.jeeves.probabilistic`.

## Temporal custody

For a target at index `t`, the model may use only observations before `t` when
constructing that target's predictive distribution. In the online ensemble, the
realized target updates model weights only after its forecast has been scored.
Those posterior weights become eligible for subsequent targets.

This is a hard contract and is covered by tail-mutation regression tests.

## Proper scoring

Point metrics such as MAE and RMSE are retained because they are intuitive, but
they cannot determine whether forecast uncertainty is honest. Jeeves therefore
uses proper distributional scores too:

- **Log score** rewards assigning high predictive density to realized outcomes.
- **CRPS** measures the distance between the full predictive CDF and realization
  while remaining in the target's physical units.
- **Pinball loss** evaluates individual predictive quantiles.
- **PIT** diagnoses distributional calibration; a calibrated continuous forecast
  should produce approximately uniform PIT values over repeated predictions.

## Robustness boundary

The robust local-linear-trend model clips the state correction produced by a large
standardized innovation. It does not pretend the shock was unlikely: likelihood
and predictive uncertainty still use the original innovation covariance. This
keeps robust state estimation separate from uncertainty accounting.

## Regime posterior

The current regime posterior is descriptive rather than causal. It summarizes
recent standardized innovations and posterior trend magnitude into probabilities
for `calm`, `trending`, `turbulent`, and `shock`. It is intended as an arbitration
signal, not as a claim that a hidden market state has been discovered.

## Calibration monitoring

Jeeves can evaluate central coverage levels (50/80/90/95 by default), predictive
sharpness, PIT shape, and sequential calibration drift. This creates an explicit
path for abstention or model rollback when uncertainty calibration deteriorates,
even when raw point error has not yet become obviously poor.

## Safety and scope

This layer:

- does not fetch external market data;
- does not call an LLM or model provider;
- does not place orders or issue financial advice;
- does not mutate Jeeves learning state;
- does not claim future predictive performance from historical fit alone.

It is mathematical evaluation infrastructure. Promotion into any live decision
path must remain a separate governed step with independent evidence and rollback.
