"""Canonical AI mathematical reference substrate.

The package is deterministic, side-effect free, and authority-neutral.  It exists
to make numerical contracts explicit and to provide a correctness oracle for
optimized runtime implementations.
"""
from .contracts import MathInvariantError, Matrix, Vector
from .linear import (
    LinearSolveReport,
    cosine_similarity,
    dot,
    l2_norm,
    matmul,
    matvec,
    solve_linear_system,
    transpose,
)
from .numerics import (
    almost_equal,
    compensated_sum,
    logsumexp,
    normalize_log_weights,
    relative_error,
    stable_mean,
    stable_softmax,
)
from .optimization import (
    OptimizationConfig,
    OptimizationResult,
    OptimizationStep,
    finite_difference_gradient,
    project,
    projected_gradient_descent,
)
from .probability import (
    cross_entropy,
    effective_sample_size,
    entropy,
    jensen_shannon_divergence,
    kl_divergence,
    normalize_distribution,
    weighted_moments,
)
from .validation import MathAuditCase, MathAuditReport, audit_runtime_kernels

__all__ = [
    "MathInvariantError",
    "Matrix",
    "Vector",
    "LinearSolveReport",
    "cosine_similarity",
    "dot",
    "l2_norm",
    "matmul",
    "matvec",
    "solve_linear_system",
    "transpose",
    "almost_equal",
    "compensated_sum",
    "logsumexp",
    "normalize_log_weights",
    "relative_error",
    "stable_mean",
    "stable_softmax",
    "OptimizationConfig",
    "OptimizationResult",
    "OptimizationStep",
    "finite_difference_gradient",
    "project",
    "projected_gradient_descent",
    "cross_entropy",
    "effective_sample_size",
    "entropy",
    "jensen_shannon_divergence",
    "kl_divergence",
    "normalize_distribution",
    "weighted_moments",
    "MathAuditCase",
    "MathAuditReport",
    "audit_runtime_kernels",
]
