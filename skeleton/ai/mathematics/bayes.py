"""Conjugate Bayesian reference updates without model or promotion authority."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum


def _count(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MathInvariantError(
            f"{name} must be a non-negative integer",
            reason="invalid_count",
            field=name,
        )
    return value


@dataclass(frozen=True, slots=True)
class BetaBinomialPosterior:
    alpha: float
    beta: float
    successes: int
    failures: int
    posterior_alpha: float
    posterior_beta: float
    mean: float
    variance: float
    log_evidence: float


def beta_binomial_posterior(
    alpha: Real,
    beta: Real,
    *,
    successes: int,
    failures: int,
) -> BetaBinomialPosterior:
    a = positive_scalar("alpha", alpha)
    b = positive_scalar("beta", beta)
    s = _count("successes", successes)
    f = _count("failures", failures)
    pa = a + s
    pb = b + f
    total = pa + pb
    mean = pa / total
    variance = pa * pb / (total * total * (total + 1.0))
    log_evidence = (
        math.lgamma(s + f + 1.0)
        - math.lgamma(s + 1.0)
        - math.lgamma(f + 1.0)
        + math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + math.lgamma(pa)
        + math.lgamma(pb)
        - math.lgamma(total)
    )
    return BetaBinomialPosterior(
        alpha=a,
        beta=b,
        successes=s,
        failures=f,
        posterior_alpha=pa,
        posterior_beta=pb,
        mean=mean,
        variance=variance,
        log_evidence=log_evidence,
    )


@dataclass(frozen=True, slots=True)
class DirichletMultinomialPosterior:
    prior_alpha: Vector
    counts: tuple[int, ...]
    posterior_alpha: Vector
    mean: Vector
    log_evidence: float


def dirichlet_multinomial_posterior(
    alpha: Sequence[Real],
    counts: Sequence[int],
) -> DirichletMultinomialPosterior:
    prior = finite_vector("alpha", alpha)
    if any(value <= 0.0 for value in prior):
        raise MathInvariantError(
            "Dirichlet concentrations must be positive",
            reason="non_positive_concentration",
            field="alpha",
        )
    clean_counts = tuple(_count(f"counts[{index}]", value) for index, value in enumerate(counts))
    if len(clean_counts) != len(prior):
        raise MathInvariantError(
            "Dirichlet concentrations and counts must align",
            reason="dimension_mismatch",
            field="counts",
        )
    posterior = tuple(a + count for a, count in zip(prior, clean_counts))
    prior_total = compensated_sum(prior)
    posterior_total = compensated_sum(posterior)
    mean = tuple(value / posterior_total for value in posterior)
    count_total = sum(clean_counts)
    log_evidence = (
        math.lgamma(count_total + 1.0)
        - compensated_sum(math.lgamma(count + 1.0) for count in clean_counts)
        + math.lgamma(prior_total)
        - math.lgamma(posterior_total)
        + compensated_sum(
            math.lgamma(post) - math.lgamma(base)
            for post, base in zip(posterior, prior)
        )
    )
    return DirichletMultinomialPosterior(
        prior_alpha=prior,
        counts=clean_counts,
        posterior_alpha=posterior,
        mean=mean,
        log_evidence=log_evidence,
    )


@dataclass(frozen=True, slots=True)
class NormalNormalPosterior:
    prior_mean: float
    prior_variance: float
    observation_variance: float
    observation_count: int
    sample_mean: float
    posterior_mean: float
    posterior_variance: float


def normal_normal_posterior(
    prior_mean: Real,
    prior_variance: Real,
    observations: Sequence[Real],
    *,
    observation_variance: Real,
) -> NormalNormalPosterior:
    mu0 = finite_scalar("prior_mean", prior_mean)
    var0 = positive_scalar("prior_variance", prior_variance)
    noise = positive_scalar("observation_variance", observation_variance)
    values = finite_vector("observations", observations)
    count = len(values)
    sample_mean = compensated_sum(values) / count
    prior_precision = 1.0 / var0
    data_precision = count / noise
    posterior_variance = 1.0 / (prior_precision + data_precision)
    posterior_mean = posterior_variance * (
        prior_precision * mu0 + data_precision * sample_mean
    )
    return NormalNormalPosterior(
        prior_mean=mu0,
        prior_variance=var0,
        observation_variance=noise,
        observation_count=count,
        sample_mean=sample_mean,
        posterior_mean=posterior_mean,
        posterior_variance=posterior_variance,
    )


@dataclass(frozen=True, slots=True)
class NormalInverseGammaPosterior:
    mean: float
    kappa: float
    alpha: float
    beta: float
    predictive_degrees_of_freedom: float
    predictive_scale: float


def normal_inverse_gamma_posterior(
    prior_mean: Real,
    prior_kappa: Real,
    prior_alpha: Real,
    prior_beta: Real,
    observations: Sequence[Real],
) -> NormalInverseGammaPosterior:
    mu0 = finite_scalar("prior_mean", prior_mean)
    kappa0 = positive_scalar("prior_kappa", prior_kappa)
    alpha0 = positive_scalar("prior_alpha", prior_alpha)
    beta0 = positive_scalar("prior_beta", prior_beta)
    values = finite_vector("observations", observations)
    n = len(values)
    mean = compensated_sum(values) / n
    scatter = compensated_sum((value - mean) ** 2 for value in values)
    kappa = kappa0 + n
    posterior_mean = (kappa0 * mu0 + n * mean) / kappa
    alpha = alpha0 + 0.5 * n
    beta = (
        beta0
        + 0.5 * scatter
        + 0.5 * (kappa0 * n / kappa) * (mean - mu0) ** 2
    )
    degrees = 2.0 * alpha
    predictive_scale = math.sqrt(beta * (kappa + 1.0) / (alpha * kappa))
    return NormalInverseGammaPosterior(
        mean=posterior_mean,
        kappa=kappa,
        alpha=alpha,
        beta=beta,
        predictive_degrees_of_freedom=degrees,
        predictive_scale=predictive_scale,
    )
