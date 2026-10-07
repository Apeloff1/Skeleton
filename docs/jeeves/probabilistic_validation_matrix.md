# Jeeves Probabilistic Validation Matrix

| Risk | Mathematical control | Regression evidence |
| --- | --- | --- |
| Future-target leakage | expanding-prefix fitting; posterior weights update after scoring | tail-mutation tests; prior/posterior custody assertions |
| Overconfident point prediction | explicit predictive variance and Gaussian mixtures | variance-growth and interval tests |
| Outlier state corruption | clipped standardized innovation in robust structural model | shock clipping regression |
| Model collapse | Bayesian weight floor plus bounded forgetting | minimum-weight tests |
| Misleading uncertainty | PIT, CRPS, coverage, sharpness, pinball loss | calibration diagnostics suite |
| Calibration drift | sequential centered-PIT CUSUM | directional drift regression |
| Numerically unstable weighting | log-space posterior update and log-sum-exp | deterministic finite-score tests |
| Incomparable model ranking | common prequential folds and proper log score | deterministic family tournament |
| Silent API churn | dedicated probabilistic facade and export tests | facade export contract |
| Accidental activation | separate promotion eligibility contract | gate rejection and evidence-count mismatch tests |

The matrix is deliberately narrower than a live prediction claim. Passing these
checks establishes implementation and evaluation discipline; it does not establish
that any model will predict future markets or other external systems reliably.
