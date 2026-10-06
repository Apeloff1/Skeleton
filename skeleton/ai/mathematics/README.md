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
- `svd.py` — thin SVD, pseudoinverse and least-norm solves with reconstruction/projection evidence.
- `quadrature2.py` — generated Gauss-Legendre rules and composite Gaussian quadrature.
- `finite_difference.py` — grid derivatives, Dirichlet Poisson solves and explicit-diffusion stability bounds.
- `entropy2.py` — Rényi/Tsallis/Gini plus mutual, conditional and variation-of-information metrics.
- `online_stats.py` — immutable mergeable streaming moment/covariance summaries.
- `wavelets.py` — orthonormal Haar and normalized Walsh-Hadamard transforms with exact inverse semantics.
- `monotone.py` — shape-preserving monotone cubic Hermite interpolation.
- `geometry2.py` — planar orientation, convex hull, polygon area/centroid and containment references.
- `krylov.py` — re-orthogonalized Arnoldi and unrestarted GMRES with explicit residual evidence.
- `tridiagonal.py` — Thomas solves and products with effective-pivot and residual diagnostics.
- `matrix_algebra2.py` — identity/trace/Frobenius/Kronecker/powers and stable signed log determinants.
- `matrix_functions.py` — scaling-and-squaring matrix exponential with convergence evidence.
- `isotonic.py` — weighted pool-adjacent-violators monotone regression with explicit block evidence.
- `proximal.py` — soft/group shrinkage plus L1/L2/L-infinity projections and elastic-net proximal maps.
- `hypothesis.py` — two-sample KS and chi-square goodness-of-fit statistics with bounded p-values.
- `smoothing.py` — local polynomial and Savitzky-Golay-style smoothing/derivative references.
- `rank_statistics.py` — average-tie ranks, Spearman, Kendall tau-b and rank-biserial references.
- `density.py` — empirical CDFs, histograms, Silverman bandwidth and weighted Gaussian KDE.
- `polynomials.py` — polynomial algebra/division/calculus and deterministic complex-root iteration.
- `interpolation_nd.py` — bilinear/trilinear regular-grid interpolation and bilinear gradients.
- `iterative_linear.py` — Jacobi, Gauss-Seidel and SOR with residual-based convergence evidence.
- `conditioning.py` — matrix norms, 1/inf condition numbers and linear backward-error reports.
- `matrix_structures.py` — Toeplitz/circulant constructors, Gershgorin discs and dominance diagnostics.
- `cosine_transforms.py` — orthonormal DCT-II/DCT-IV plus separable 2-D DCT round trips.
- `bayes.py` — conjugate Beta/Binomial, Dirichlet/Multinomial, Normal/Normal and Normal-Inverse-Gamma posterior math.
- `interval.py` — finite conservative interval arithmetic with outward rounding and domain checks.
- `orthogonal.py` — Givens rotations and Householder reflectors with explicit orthogonal transforms.
- `ldlt.py` — symmetric LDL^T factorization/solve with inertia and reconstruction evidence.
- `bsplines.py` — Cox-de Boor B-spline bases, clamped uniform knots and vector-valued curves.
- `whitening.py` — PCA/ZCA covariance whitening with eigenvalue and covariance-residual evidence.
- `finite_difference2d.py` — 2-D gradient, divergence, Laplacian and scalar curl finite differences.
- `matrix_updates.py` — symmetric rank-one updates plus Cholesky update/downdate reconstruction evidence.
- `matrix_equations.py` — dense Sylvester and continuous Lyapunov solves with equation residual evidence.
- `symmetric_functions.py` — spectral square-root/inverse-root/log/exp functions for symmetric matrices.
- `hyperdual.py` — exact small-problem gradients/Hessians through hyper-dual second-order differentiation.
- `orthogonal_polynomials.py` — Chebyshev/Legendre/Hermite recurrences, Clenshaw evaluation and fitted Chebyshev series.
- `tensor_contract.py` — explicit-axis dense tensor contraction, outer/dot and mode products.
- `finite_element1d.py` — linear-element mass/stiffness assembly and Dirichlet Poisson solves.
- `covariance_shrinkage.py` — identity/diagonal covariance shrinkage and OAS regularization evidence.
- `low_rank.py` — truncated-SVD approximation and retained-energy rank selection.
- `bezier.py` — de Casteljau Bezier evaluation, exact derivative curves, subdivision and control bounds.
- `continuous_distributions.py` — regularized beta/gamma functions and Beta/Gamma/Dirichlet density-CDF references.
- `inference_tests.py` — Welch t, Mann-Whitney U and one-way ANOVA diagnostics with explicit test evidence.
- `derivative_free.py` — bounded golden-section and deterministic Nelder-Mead minimization references.
- `control_math.py` — controllability/observability ranks, zero-order-hold discretization and continuous Gramians.
- `matrix_scaling.py` — deterministic row/column max-norm equilibration with explicit scaling evidence.
- `acceleration.py` — bounded fixed-point iteration and regularized Anderson acceleration.
- `cubature.py` — tensor-product Gauss-Legendre cubature over bounded hyperrectangles.
- `sparse_iterative.py` — PCG/Jacobi and BiCGSTAB solvers over canonical CSR with explicit Krylov breakdown evidence.
- `fft_blocks.py` — FFT convolution, overlap-add streaming convolution and FFT cross-correlation on canonical radix-2 transforms.
- `gaussian_process.py` — zero-mean GP posterior covariance and log-marginal evidence over canonical kernels/Cholesky.
- `kalman.py` — linear-Gaussian Kalman filtering and Rauch-Tung-Striebel smoothing with Joseph covariance updates.
- `pde_time.py` — periodic upwind advection, explicit diffusion and leapfrog wave integration with CFL gates.
- `spherical.py` — unit-sphere geodesic distance, log/exp maps and shortest-arc interpolation.
- `markov_diagnostics.py` — total variation, Dobrushin contraction, detailed balance and finite-step mixing profiles.
- `design_sampling.py` — deterministic Latin-hypercube designs, centered L2 discrepancy and bounded rescaling.
- `sde.py` — seeded Euler-Maruyama/Milstein scalar SDE paths plus closed-form geometric-Brownian moments.
- `matrix_frechet.py` — block-exponential Fréchet derivatives with centered finite-difference evidence and condition proxies.
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
- SVD keeps numerical rank explicit and verifies both reconstruction and Moore-Penrose projection identities.
- Gaussian quadrature derives its own Legendre nodes/weights and bounds supported order explicitly.
- Finite-difference PDE helpers expose their sign convention, boundary conditions and residual evidence.
- Generalized information metrics normalize joint distributions explicitly and reject contradictory support.
- Streaming statistics are immutable/mergeable so parallel accumulation preserves deterministic summary semantics.
- Haar and Hadamard transforms are orthonormal and expose explicit inverse operations.
- Monotone cubic interpolation applies slope limiting so monotonic samples do not acquire overshoot.
- Planar geometry uses deterministic hull ordering and explicit boundary-inclusion semantics.
- Krylov methods re-orthogonalize explicitly and report residual-based convergence rather than trusting iteration count.
- Tridiagonal solves expose the smallest effective pivot and reject unstable elimination.
- Matrix algebra separates stable signed log-determinants from overflow-prone raw determinants.
- Matrix exponential scaling/Taylor/squaring exposes convergence, term count and scaling depth.
- Isotonic regression keeps its pooled monotone blocks and weighted residual objective inspectable.
- Proximal operators make norm-ball constraints and regularization weights explicit rather than hiding optimizer policy.
- Hypothesis diagnostics expose the statistic, degrees/sample counts and bounded asymptotic probability evidence.
- Local polynomial smoothing fits edge windows explicitly rather than silently truncating kernels.
- Rank statistics carry tie semantics explicitly and fail closed when concordance is undefined.
- Density estimators expose support, binning and bandwidth choices instead of hiding estimator policy.
- Polynomial roots report convergence/update/residual evidence rather than returning unqualified roots.
- Multi-dimensional interpolation rejects extrapolation and shape mismatch at the public boundary.
- Stationary linear solvers expose residual convergence and reject zero diagonals or invalid relaxation factors.
- Conditioning diagnostics distinguish matrix norm growth from actual backward error and verify inverse residuals.
- Structured-matrix helpers keep Toeplitz/circulant indexing and Gershgorin radii deterministic.
- Cosine transforms use orthonormal conventions so inverse and energy semantics are explicit.
- Conjugate Bayesian helpers return posterior/evidence math only and never own learned state or promotion.
- Interval arithmetic rounds outward and rejects zero-divisor/domain-crossing intervals rather than pretending point precision.
- Orthogonal primitives expose the exact reflector/rotation parameters used by higher-level decomposition oracles.
- LDL^T reports reconstruction and pivot-sign inertia and fails closed when unpivoted factorization is unsafe.
- B-spline evaluation exposes partition-of-unity and active-basis evidence and forbids hidden extrapolation.
- Whitening distinguishes PCA/ZCA semantics and verifies the transformed covariance against the regularized target.
- 2-D finite differences make grid orientation, spacing and boundary stencils explicit.
- Rank-one Cholesky updates verify reconstructed targets and fail closed when a downdate would lose positive definiteness.
- Matrix-equation solvers expose equation residuals and keep state-estimation/control authority outside this layer.
- Symmetric matrix functions validate spectral domains before applying roots, inverse roots or logarithms.
- Hyper-dual calculus provides exact second-order oracle derivatives without becoming a training graph executor.
- Orthogonal-polynomial series expose coefficient/sample semantics and forbid silent fit-domain extrapolation.
- Tensor contraction validates every contracted axis and keeps scalar outputs in the package's canonical singleton representation.
- Finite-element assembly exposes mass/stiffness symmetry, exact Dirichlet boundaries and algebraic residual evidence.
- Covariance shrinkage keeps target/intensity/eigenspectrum explicit rather than hiding regularization policy.
- Low-rank approximations report discarded Frobenius energy and never reinterpret rank as model capacity authority.
- Bezier geometry uses de Casteljau subdivision so curve evaluation and splitting share one deterministic construction.
- Continuous distributions keep special-function convergence/domain checks explicit and do not create predictive authority.
- Statistical inference reports test statistics/degrees/effect structure and keeps decision thresholds outside this layer.
- Derivative-free solvers are bounded reference optimizers and do not own model training or parameter promotion.
- Linear-control mathematics reports rank/Gramian/discretization evidence only and never owns runtime control authority.
- Matrix equilibration exposes both diagonal scales and post-scaling row/column norm errors.
- Anderson acceleration regularizes its residual Gram system and falls back deterministically on singular history.
- Cubature bounds dimensionality and panel/order semantics so evaluation growth remains explicit.
- Sparse iterative solvers reuse canonical CSR storage and fail closed on PCG symmetry/curvature or BiCGSTAB breakdown.
- FFT block convolution reuses canonical radix-2 transforms and exposes block-size semantics instead of introducing a parallel FFT.
- Gaussian-process helpers expose posterior covariance/evidence only; kernel learning and model promotion remain outside this layer.
- Kalman/RTS math exposes innovations, gains and covariances without assuming runtime control or tracking authority.
- Time-domain PDE references reject CFL-unstable steps instead of returning numerically plausible but invalid trajectories.
- Spherical geometry rejects antipodal ambiguity and non-tangent exponential-map inputs explicitly.
- Markov diagnostics reuse canonical transition/stationary semantics and expose contraction/reversibility rather than redefining graph authority.
- Latin-hypercube design complements canonical Halton sampling and reports spacing/discrepancy evidence deterministically.
- SDE references use the canonical seeded generator and expose every Brownian increment; no stochastic runtime authority is introduced.
- Matrix-exponential Fréchet derivatives use the exact block identity and carry an independent centered-difference residual.
- `audit_runtime_kernels()` compares optimized runtime softmax, matmul and attention against
  this reference substrate without replacing those kernels.

## Promotion rule

Optimized NumPy/native/GPU/SymPy/formal backends may be added above this package,
but they must demonstrate parity or stronger invariants against this reference
layer. Optional backend availability must never change the meaning of the
reference contract.
