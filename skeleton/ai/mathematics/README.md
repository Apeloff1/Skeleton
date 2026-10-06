# AI mathematics reference substrate

This package is the canonical, AI-native mathematical **reference** layer. It is
not a model, router, knowledge store, optimizer authority, or promotion plane.

## Reverse-engineering basis

The build was derived from three existing repository surfaces:

1. the quarantined `research/legacy/gameforge/math_exocortex` lineage, which
   demonstrated calculator, uncertainty, symbolic/formal-tooling, and mechanics
   ambitions but is explicitly non-authoritative;
2. the optimized `runtime/kernel/ops` math paths, which need a small,
   deterministic correctness oracle for numerical parity;
3. the Jeeves probabilistic stack, whose evidence custody already requires
   finite values, explicit calibration identities, and fail-closed validation.

The result intentionally does **not** copy the legacy exocortex into production.
It extracts the reusable contract: deterministic finite math, explicit dimensions,
stable normalization, auditable optimization, and invariant checks.

## Guarantees

- Python standard library only; no optional dependency is required for correctness.
- NaN and infinity are rejected at public boundaries.
- Dense matrix operations reject ragged and dimension-mismatched inputs.
- Probability operations normalize explicitly and reject missing support where a
  finite divergence cannot be justified.
- Optimization is deterministic, bounded by iteration/line-search limits, and
  records a trace rather than silently claiming convergence.
- `audit_runtime_kernels()` compares the optimized runtime softmax, matmul, and
  attention row against this reference substrate without replacing those kernels.

## Promotion rule

Optimized NumPy/native/GPU/SymPy/formal backends may be added above this package,
but they must demonstrate parity or stronger invariants against this reference
layer. Optional backend availability must never change the meaning of the
reference contract.
