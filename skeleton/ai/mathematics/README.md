# AI mathematics reference substrate

This package is the canonical, AI-native mathematical **reference** layer. It is
not a model, router, knowledge store, optimizer authority, or promotion plane.

## Reverse-engineering basis

The build is derived from existing repository contracts rather than inventing a
parallel AI stack:

1. the quarantined `research/legacy/gameforge/math_exocortex` lineage, which
   demonstrates calculator, uncertainty, symbolic/formal-tooling, and mechanics
   ambitions but is explicitly non-authoritative;
2. optimized `runtime/kernel/ops` and `runtime/cortex/attn.py` primitives,
   which need deterministic correctness oracles for numerics, tensor shapes,
   attention-supporting algebra, and differentiation;
3. the Jeeves probabilistic and spectral stack, whose evidence custody requires
   finite values, explicit dimensionality, calibration identity, and leakage-safe
   mathematical behavior;
4. local recurrent-model training, which already owns model learning and therefore
   must not be duplicated by this package.

The result intentionally does **not** copy the legacy exocortex into production.
It extracts reusable mathematical contracts while preserving existing runtime and
model authority boundaries.

## Implemented reference domains

- `contracts.py` — finite scalar/vector/matrix validation and dimension errors.
- `numerics.py` — compensated summation, log-sum-exp, stable softmax and error metrics.
- `linear.py` — dense reference algebra and pivoted linear solve evidence.
- `probability.py` — normalized probability and information-theory invariants.
- `optimization.py` — bounded deterministic projected-gradient reference solver.
- `autodiff.py` — multi-direction dual numbers, exact first derivatives and Jacobians.
- `tensor.py` — immutable row-major dense tensors, reshape, transpose and broadcasting.
- `spectral.py` — symmetric dominant eigenpair and deterministic periodogram diagnostics.
- `integration.py` — adaptive Simpson quadrature and bounded fixed-step RK4 dynamics.
- `statistics.py` — Welford moments, covariance/correlation, robust quantiles and MAD.
- `graph.py` — validated Laplacians, random-walk matrices and stationary-distribution evidence.
- `solvers.py` — bracketed roots and SPD conjugate gradient with explicit residual reports.
- `sampling.py` — deterministic SplitMix64, systematic resampling, Halton points and Monte Carlo error.
- `geometry.py` — Euclidean/angular metrics, simplex projection, barycentric and subspace projection.
- `losses.py` — stable regression/classification losses and logit-domain cross entropy.
- `sparse.py` — canonical CSR storage, COO duplicate reduction, sparse matvec/transpose/dense products.
- `approximation.py` — Horner evaluation, Chebyshev nodes, barycentric/Newton and piecewise interpolation.
- `distributions.py` — Normal, Student-t, Bernoulli, Poisson and Gaussian-mixture density references.
- `transforms.py` — DFT, radix-2 FFT, inverse transforms, convolution and autocorrelation.
- `calibration_metrics.py` — ECE/MCE/Brier metrics only; no calibration ledger or correction authority.
- `decompositions.py` — Cholesky, re-orthogonalized thin QR, SPD solve and full-rank least squares.
- `calculus2.py` — finite-difference Hessian, gradient and quadratic local-model diagnostics.
- `kernels.py` — linear/polynomial/RBF/Laplacian kernels, Gram centering and MMD reference tests.
- `information_geometry.py` — TV, Hellinger, Bhattacharyya, Fisher-Rao and Mahalanobis distances.
- `sequence.py` — Levenshtein, DTW with explicit alignment path, and discrete Fréchet distance.
- `eigensystems.py` — full symmetric Jacobi eigensystems and covariance PCA with reconstruction evidence.
- `differentiation.py` — Richardson scalar derivatives, finite-difference Jacobians and gradient checks.
- `optimization2.py` — damped Newton and BFGS references with deterministic Armijo line search.
- `integration2.py` — adaptive Dormand-Prince RK45 with accepted/rejected-step evidence.
- `robust.py` — trimmed/winsorized location, MAD scale, Huber location and modified-z diagnostics.
- `resampling.py` — deterministic jackknife and seeded bootstrap uncertainty reports.
- `stochastic.py` — finite-state propagation, transition powers, hitting times and absorption probabilities.
- `matching.py` — deterministic rectangular minimum-cost bipartite assignment.
- `lu.py` — pivoted LU, solves, determinant and inverse with reconstruction/identity residuals.
- `splines.py` — natural cubic splines with derivatives and exact piecewise polynomial integrals.
- `transport.py` — weighted 1D Wasserstein distance and entropy-regularized Sinkhorn plans.
- `rotations.py` — quaternion composition, axis-angle conversion, vector rotation, SLERP and matrices.
- `combinatorics.py` — exact counts plus stable binomial, hypergeometric and multinomial log masses.
- `special_functions.py` — stable log-domain arithmetic, sigmoid/logit, softplus inverse and log-cosh.
- `signal2.py` — standard windows, cross-correlation, rolling mean/RMS and linear detrending.
- `distances.py` — Minkowski/Canberra/Bray-Curtis/cosine and set/weighted-Jaccard reference metrics.
- `validation.py` — parity evidence against existing optimized runtime kernels.

## Guarantees

- Python standard library only; no optional dependency is required for correctness.
- NaN and infinity are rejected at public boundaries.
- Dense matrix/tensor operations reject ragged, invalid-index and dimension-mismatched input.
- Broadcasting follows explicit right-aligned compatibility rules.
- Probability operations normalize explicitly and reject missing support where finite
  divergence cannot be justified.
- Automatic differentiation rejects silent derivative-dimension changes.
- Spectral eigen analysis reports residuals and convergence instead of merely returning a vector.
- Quadrature reports an error estimate/evaluation count; RK4 validates every derivative state.
- Optimization and root/linear solvers are deterministic, bounded, and expose residual/convergence evidence.
- Graph mathematics validates stochasticity/symmetry rather than assuming graph-runtime invariants.
- Sampling is explicitly seeded and reproducible; quasi-random sequences have fixed index semantics.
- Geometry projection rejects degenerate or rank-deficient constructions instead of hiding them.
- Training losses operate in stable logit/log domains and reject impossible support.
- Sparse matrices have one canonical CSR representation; duplicate COO coordinates are merged deterministically.
- Approximation routines reject duplicate/non-monotonic nodes and make extrapolation policy explicit.
- Distribution routines expose density/CDF math only and do not create predictive-model ownership.
- Transform paths provide an O(n^2) DFT oracle beside radix-2 FFT so optimized paths can be parity checked.
- Calibration helpers are read-only metrics; evidence ledgers and confidence correction remain in their existing owners.
- Matrix decompositions expose reconstruction/orthogonality/residual evidence and reject numerical rank loss.
- Second-order calculus is an oracle layer only; it does not own training steps, optimizers, or parameter updates.
- Kernels and MMD measure similarity/distribution shift but do not fit or promote models.
- Information geometry normalizes distributions explicitly and uses SPD covariance solves for Mahalanobis distance.
- Sequence metrics return deterministic edit/alignment/trajectory distances without taking retrieval or ranking authority.
- Full eigensystems and PCA expose orthogonality/reconstruction evidence rather than silently trusting decomposition output.
- Numerical differentiation explicitly detects output-shape drift and can cross-check analytic/autodiff gradients.
- Second-order/quasi-Newton optimizers are reference solvers only and do not own model parameter updates.
- Adaptive RK45 records accepted/rejected steps and fails closed on dimension or tolerance violations.
- Robust estimators expose convergence/scale rather than silently masking degenerate samples.
- Resampling uncertainty is explicitly seeded and carries its replicate evidence.
- Stochastic-process analysis validates row-stochastic matrices and fails closed on infinite hitting-time systems.
- Assignment solves cover the complete smaller partition with deterministic tie handling and explicit total cost.
- LU exposes permutation/reconstruction evidence and matrix inversion verifies the identity residual.
- Natural splines keep interpolation, derivative and integration semantics inside the knot domain unless clamp is explicit.
- Optimal transport normalizes marginals explicitly and records Sinkhorn marginal residuals/convergence.
- Quaternion operations normalize rotations and reject zero-axis/zero-norm ambiguities.
- Discrete mass functions preserve exact combinatorial support and fail closed instead of returning silent infinities.
- Stable scalar transforms keep log-domain subtraction/complements numerically meaningful near probability boundaries.
- Signal diagnostics make window length and normalization contracts explicit and use least-squares detrending.
- Distance primitives distinguish metric-domain assumptions such as non-negative weighted Jaccard inputs.
- `audit_runtime_kernels()` compares optimized runtime softmax, matmul and attention against
  this reference substrate without replacing those kernels.

## Promotion rule

Optimized NumPy/native/GPU/SymPy/formal backends may be added above this package,
but they must demonstrate parity or stronger invariants against this reference
layer. Optional backend availability must never change the meaning of the
reference contract.
