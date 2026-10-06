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
- `audit_runtime_kernels()` compares optimized runtime softmax, matmul and attention against
  this reference substrate without replacing those kernels.

## Promotion rule

Optimized NumPy/native/GPU/SymPy/formal backends may be added above this package,
but they must demonstrate parity or stronger invariants against this reference
layer. Optional backend availability must never change the meaning of the
reference contract.
