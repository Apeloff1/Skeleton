"""Bayesian discrete mechanism learning from verified interventions.

The original causal kernel intentionally started with a small categorical
learner.  This module provides the stronger production path.  It respects
intervention semantics explicitly:

* interventions on *parents* are valid parent assignments;
* interventions on the *child* remove that sample from mechanism estimation;
* unverified transitions never train promoted mechanisms;
* weighted samples contribute fractional counts and effective sample size;
* Dirichlet posteriors expose uncertainty instead of only point estimates;
* temporal holdout reports log loss, Brier score and calibration error;
* local BDeu scores compare candidate parent sets with a complexity-aware
  Bayesian marginal likelihood;
* promotion is a typed proposal/gate rather than an automatic mutation.

This is a local, discrete mechanism learner.  It does not claim causal
identification from observational data alone; parent-set structure still needs
interventional evidence or other identification assumptions.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .causal_epistemics import (
    CategoricalDistribution,
    CausalMechanism,
    MechanismRow,
    MechanismStatus,
    StructuralCausalModel,
    TransitionSample,
)
from .types import (
    AgentContractError,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


_EPS = 1e-12


class InterventionalLearningError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DirichletPosterior:
    support: tuple[str, ...]
    alpha: Mapping[str, float]
    weighted_count: float

    def __post_init__(self) -> None:
        support = tuple(str(item) for item in self.support)
        if not support or len(set(support)) != len(support):
            raise AgentContractError("Dirichlet support must be unique and non-empty")
        alpha = {str(key): finite_number(f"alpha[{key}]", value) for key, value in dict(self.alpha).items()}
        if set(alpha) != set(support) or any(value <= 0 for value in alpha.values()):
            raise AgentContractError("Dirichlet alpha must be positive over exact support")
        object.__setattr__(self, "support", support)
        object.__setattr__(self, "alpha", alpha)
        weighted = finite_number("weighted_count", self.weighted_count)
        if weighted < 0:
            raise AgentContractError("weighted_count must be non-negative")
        object.__setattr__(self, "weighted_count", weighted)

    @property
    def total_alpha(self) -> float:
        return sum(self.alpha.values())

    @property
    def mean(self) -> CategoricalDistribution:
        return CategoricalDistribution(dict(self.alpha), self.support)

    def variance(self, value: str) -> float:
        a = self.alpha[value]
        total = self.total_alpha
        return a * (total - a) / (total * total * (total + 1.0))

    @property
    def mean_variance(self) -> float:
        return statistics.fmean(self.variance(value) for value in self.support)

    @property
    def concentration(self) -> float:
        return self.total_alpha

    def as_json(self) -> dict[str, Any]:
        return {
            "support": list(self.support),
            "alpha": dict(self.alpha),
            "weighted_count": self.weighted_count,
            "mean": self.mean.as_json(),
            "mean_variance": self.mean_variance,
        }


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    accuracy: float
    gap: float


@dataclass(frozen=True, slots=True)
class PredictiveMetrics:
    count: int
    weighted_count: float
    log_loss: float
    brier_score: float
    expected_calibration_error: float
    maximum_calibration_error: float
    accuracy: float
    bins: tuple[CalibrationBin, ...]


@dataclass(frozen=True, slots=True)
class LocalStructureScore:
    child_id: str
    parent_ids: tuple[str, ...]
    bdeu_log_score: float
    parameter_count: int
    observed_parent_configurations: int
    usable_samples: int
    interventional_parent_samples: int
    observational_samples: int
    child_intervention_exclusions: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class MechanismTrainingReport:
    report_id: str
    child_id: str
    parent_ids: tuple[str, ...]
    mechanism: CausalMechanism
    row_posteriors: Mapping[tuple[tuple[str, str], ...], DirichletPosterior]
    fallback_posterior: DirichletPosterior
    train_sample_ids: tuple[str, ...]
    holdout_sample_ids: tuple[str, ...]
    excluded_unverified: int
    excluded_child_interventions: int
    excluded_missing_values: int
    interventional_parent_samples: int
    observational_samples: int
    effective_sample_size: float
    metrics: PredictiveMetrics | None
    structure_score: LocalStructureScore
    confidence: float
    promotable: bool
    reasons: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class MechanismTrainingPolicy:
    equivalent_sample_size: float = 4.0
    minimum_train_samples: int = 8
    minimum_effective_sample_size: float = 6.0
    minimum_interventional_parent_samples: int = 2
    holdout_fraction: float = 0.20
    minimum_confidence: float = 0.45
    maximum_log_loss: float = 3.5
    maximum_brier_score: float = 0.40
    maximum_ece: float = 0.30
    calibration_bins: int = 8
    maximum_parent_count: int = 6

    def __post_init__(self) -> None:
        ess = finite_number("equivalent_sample_size", self.equivalent_sample_size)
        if ess <= 0:
            raise AgentContractError("equivalent_sample_size must be positive")
        object.__setattr__(self, "equivalent_sample_size", ess)
        object.__setattr__(self, "minimum_train_samples", positive_int("minimum_train_samples", self.minimum_train_samples, maximum=1_000_000))
        min_ess = finite_number("minimum_effective_sample_size", self.minimum_effective_sample_size)
        if min_ess <= 0:
            raise AgentContractError("minimum_effective_sample_size must be positive")
        object.__setattr__(self, "minimum_effective_sample_size", min_ess)
        object.__setattr__(self, "minimum_interventional_parent_samples", positive_int("minimum_interventional_parent_samples", self.minimum_interventional_parent_samples, maximum=1_000_000))
        object.__setattr__(self, "holdout_fraction", probability("holdout_fraction", self.holdout_fraction))
        object.__setattr__(self, "minimum_confidence", probability("minimum_confidence", self.minimum_confidence))
        for name in ("maximum_log_loss", "maximum_brier_score", "maximum_ece"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "calibration_bins", positive_int("calibration_bins", self.calibration_bins, maximum=100))
        object.__setattr__(self, "maximum_parent_count", positive_int("maximum_parent_count", self.maximum_parent_count, maximum=32))


@dataclass(frozen=True, slots=True)
class _ResolvedSample:
    sample: TransitionSample
    parent_assignment: tuple[tuple[str, str], ...]
    child_value: str
    parent_intervened: bool


class InterventionalSampleResolver:
    """Resolve causal transition records without losing do() semantics."""

    @staticmethod
    def value_for(sample: TransitionSample, variable_id: str) -> str | None:
        # An intervention is the authoritative assignment for an intervened
        # variable.  Next-state values outrank prior-state observations for
        # ordinary transition parents; prior state is the final fallback.
        if variable_id in sample.interventions:
            return sample.interventions[variable_id]
        if variable_id in sample.after:
            return sample.after[variable_id]
        return sample.before.get(variable_id)

    def resolve(
        self,
        sample: TransitionSample,
        *,
        child_id: str,
        parent_ids: Sequence[str],
        child_domain: Sequence[str],
        parent_domains: Mapping[str, Sequence[str]],
    ) -> _ResolvedSample | None:
        if not sample.verified:
            return None
        # do(child=value) severs the natural parent -> child mechanism.  Such a
        # transition is evidence about the intervention, not about the child CPD.
        if child_id in sample.interventions:
            return None
        child_value = sample.after.get(child_id)
        if child_value is None or child_value not in child_domain:
            return None
        assignment: list[tuple[str, str]] = []
        parent_intervened = False
        for parent_id in parent_ids:
            value = self.value_for(sample, parent_id)
            if value is None or value not in parent_domains[parent_id]:
                return None
            assignment.append((parent_id, value))
            parent_intervened = parent_intervened or parent_id in sample.interventions
        return _ResolvedSample(
            sample=sample,
            parent_assignment=tuple(sorted(assignment)),
            child_value=child_value,
            parent_intervened=parent_intervened,
        )


class BayesianMechanismTrainer:
    def __init__(
        self,
        model: StructuralCausalModel,
        *,
        policy: MechanismTrainingPolicy | None = None,
    ) -> None:
        self.model = model
        self.policy = policy or MechanismTrainingPolicy()
        self.resolver = InterventionalSampleResolver()

    def train(
        self,
        child_id: str,
        parent_ids: Sequence[str],
        samples: Sequence[TransitionSample],
        *,
        regime: str = "default",
    ) -> MechanismTrainingReport:
        child = self.model.variable(child_id)
        parents = tuple(require_id("parent_id", item) for item in parent_ids)
        if len(parents) > self.policy.maximum_parent_count:
            raise InterventionalLearningError("candidate parent set exceeds policy")
        if child_id in parents or len(set(parents)) != len(parents):
            raise InterventionalLearningError("invalid candidate parent set")
        parent_domains = {parent: self.model.variable(parent).domain for parent in parents}

        resolved: list[_ResolvedSample] = []
        excluded_unverified = excluded_child = excluded_missing = 0
        for sample in sorted(samples, key=lambda item: (item.observed_at, item.sample_id)):
            if sample.regime != regime:
                continue
            if not sample.verified:
                excluded_unverified += 1
                continue
            if child_id in sample.interventions:
                excluded_child += 1
                continue
            item = self.resolver.resolve(
                sample,
                child_id=child_id,
                parent_ids=parents,
                child_domain=child.domain,
                parent_domains=parent_domains,
            )
            if item is None:
                excluded_missing += 1
                continue
            resolved.append(item)

        holdout_count = 0
        if len(resolved) >= max(self.policy.minimum_train_samples + 2, 10):
            holdout_count = max(1, round(len(resolved) * self.policy.holdout_fraction))
            holdout_count = min(holdout_count, len(resolved) - self.policy.minimum_train_samples)
        train = resolved[:-holdout_count] if holdout_count else resolved
        holdout = resolved[-holdout_count:] if holdout_count else []

        row_posteriors = self._fit_rows(child.domain, parents, parent_domains, train)
        fallback = self._fit_fallback(child.domain, train)
        rows = tuple(
            MechanismRow(parent_values=key, distribution=posterior.mean)
            for key, posterior in sorted(row_posteriors.items())
        )
        effective_n = self._effective_sample_size([item.sample.weight for item in train])
        parent_interventions = sum(1 for item in train if item.parent_intervened)
        observational = len(train) - parent_interventions
        confidence = self._confidence(
            sample_count=len(train),
            effective_n=effective_n,
            parent_interventions=parent_interventions,
            row_posteriors=row_posteriors,
        )
        mechanism = CausalMechanism(
            child_id=child_id,
            parent_ids=parents,
            rows=rows,
            fallback=fallback.mean,
            status=MechanismStatus.PROVISIONAL,
            confidence=confidence,
            sample_count=len(train),
            regime=regime,
            provenance=tuple(item.sample.sample_id for item in train),
            metadata={
                "trainer": "bayesian-interventional-v1",
                "equivalent_sample_size": self.policy.equivalent_sample_size,
                "effective_sample_size": effective_n,
                "parent_intervention_samples": parent_interventions,
            },
        )
        metrics = self._evaluate(mechanism, holdout, child.domain) if holdout else None
        structure_score = self.local_bdeu_score(child_id, parents, samples, regime=regime)
        promotable, reasons = self._promotion_decision(
            train_count=len(train),
            effective_n=effective_n,
            parent_interventions=parent_interventions,
            confidence=confidence,
            metrics=metrics,
        )
        report_id = stable_id(
            "mechanism-training",
            {
                "child": child_id,
                "parents": parents,
                "train": [item.sample.sample_id for item in train],
                "holdout": [item.sample.sample_id for item in holdout],
                "mechanism": mechanism.fingerprint,
            },
        )
        fingerprint = stable_fingerprint(
            {
                "report": report_id,
                "mechanism": mechanism.fingerprint,
                "confidence": confidence,
                "promotable": promotable,
                "metrics": self._metrics_json(metrics),
                "structure": structure_score.fingerprint,
            }
        )
        return MechanismTrainingReport(
            report_id=report_id,
            child_id=child_id,
            parent_ids=parents,
            mechanism=mechanism,
            row_posteriors=row_posteriors,
            fallback_posterior=fallback,
            train_sample_ids=tuple(item.sample.sample_id for item in train),
            holdout_sample_ids=tuple(item.sample.sample_id for item in holdout),
            excluded_unverified=excluded_unverified,
            excluded_child_interventions=excluded_child,
            excluded_missing_values=excluded_missing,
            interventional_parent_samples=parent_interventions,
            observational_samples=observational,
            effective_sample_size=effective_n,
            metrics=metrics,
            structure_score=structure_score,
            confidence=confidence,
            promotable=promotable,
            reasons=reasons,
            fingerprint=fingerprint,
        )

    def _fit_rows(
        self,
        child_domain: Sequence[str],
        parent_ids: Sequence[str],
        parent_domains: Mapping[str, Sequence[str]],
        samples: Sequence[_ResolvedSample],
    ) -> Mapping[tuple[tuple[str, str], ...], DirichletPosterior]:
        counts: defaultdict[tuple[tuple[str, str], ...], Counter[str]] = defaultdict(Counter)
        for item in samples:
            counts[item.parent_assignment][item.child_value] += item.sample.weight
        q = 1
        for parent_id in parent_ids:
            q *= len(parent_domains[parent_id])
        prior_per_cell = self.policy.equivalent_sample_size / max(1, q * len(child_domain))
        posteriors: dict[tuple[tuple[str, str], ...], DirichletPosterior] = {}
        for key, row_counts in counts.items():
            alpha = {
                value: prior_per_cell + row_counts.get(value, 0.0)
                for value in child_domain
            }
            posteriors[key] = DirichletPosterior(
                tuple(child_domain),
                alpha,
                weighted_count=sum(row_counts.values()),
            )
        return posteriors

    def _fit_fallback(
        self,
        child_domain: Sequence[str],
        samples: Sequence[_ResolvedSample],
    ) -> DirichletPosterior:
        counts: Counter[str] = Counter()
        for item in samples:
            counts[item.child_value] += item.sample.weight
        prior = self.policy.equivalent_sample_size / len(child_domain)
        return DirichletPosterior(
            tuple(child_domain),
            {value: prior + counts.get(value, 0.0) for value in child_domain},
            weighted_count=sum(counts.values()),
        )

    @staticmethod
    def _effective_sample_size(weights: Sequence[float]) -> float:
        if not weights:
            return 0.0
        total = sum(weights)
        squares = sum(weight * weight for weight in weights)
        if squares <= 0:
            return 0.0
        return total * total / squares

    def _confidence(
        self,
        *,
        sample_count: int,
        effective_n: float,
        parent_interventions: int,
        row_posteriors: Mapping[tuple[tuple[str, str], ...], DirichletPosterior],
    ) -> float:
        count_term = 1.0 - math.exp(-effective_n / 20.0)
        intervention_term = 1.0 - math.exp(-parent_interventions / 6.0)
        uncertainty = statistics.fmean(
            (posterior.mean_variance for posterior in row_posteriors.values()),
        ) if row_posteriors else 0.25
        certainty_term = max(0.0, min(1.0, 1.0 - uncertainty * 8.0))
        coverage_term = min(1.0, len(row_posteriors) / max(1.0, math.sqrt(max(1, sample_count))))
        return max(
            0.0,
            min(
                0.995,
                0.35 * count_term
                + 0.30 * intervention_term
                + 0.20 * certainty_term
                + 0.15 * coverage_term,
            ),
        )

    def _evaluate(
        self,
        mechanism: CausalMechanism,
        holdout: Sequence[_ResolvedSample],
        child_domain: Sequence[str],
    ) -> PredictiveMetrics:
        rows: list[tuple[float, float, bool, float]] = []
        # tuple(weight, confidence of predicted class, correct, squared error sum)
        log_loss_sum = brier_sum = weight_sum = correct_sum = 0.0
        confidences: list[tuple[float, bool, float]] = []
        for item in holdout:
            distribution = mechanism.distribution_for(dict(item.parent_assignment))
            truth = item.child_value
            p_truth = max(_EPS, distribution.probability_of(truth))
            weight = item.sample.weight
            log_loss_sum += -math.log(p_truth) * weight
            brier = sum(
                (distribution.probability_of(value) - (1.0 if value == truth else 0.0)) ** 2
                for value in child_domain
            ) / len(child_domain)
            brier_sum += brier * weight
            predicted = distribution.mode
            correct = predicted == truth
            correct_sum += (1.0 if correct else 0.0) * weight
            confidence = distribution.maximum_probability
            confidences.append((confidence, correct, weight))
            weight_sum += weight
        ece, mce, bins = self._calibration(confidences)
        denominator = max(_EPS, weight_sum)
        return PredictiveMetrics(
            count=len(holdout),
            weighted_count=weight_sum,
            log_loss=log_loss_sum / denominator,
            brier_score=brier_sum / denominator,
            expected_calibration_error=ece,
            maximum_calibration_error=mce,
            accuracy=correct_sum / denominator,
            bins=bins,
        )

    def _calibration(
        self,
        rows: Sequence[tuple[float, bool, float]],
    ) -> tuple[float, float, tuple[CalibrationBin, ...]]:
        if not rows:
            return 0.0, 0.0, ()
        total_weight = sum(weight for _, _, weight in rows)
        output: list[CalibrationBin] = []
        ece = mce = 0.0
        for index in range(self.policy.calibration_bins):
            lower = index / self.policy.calibration_bins
            upper = (index + 1) / self.policy.calibration_bins
            members = [
                row
                for row in rows
                if lower <= row[0] <= upper
                if index == self.policy.calibration_bins - 1 or row[0] < upper
            ]
            if not members:
                continue
            weight = sum(item[2] for item in members)
            mean_conf = sum(item[0] * item[2] for item in members) / weight
            accuracy = sum((1.0 if item[1] else 0.0) * item[2] for item in members) / weight
            gap = abs(mean_conf - accuracy)
            ece += gap * weight / max(_EPS, total_weight)
            mce = max(mce, gap)
            output.append(CalibrationBin(lower, upper, len(members), mean_conf, accuracy, gap))
        return ece, mce, tuple(output)

    def _promotion_decision(
        self,
        *,
        train_count: int,
        effective_n: float,
        parent_interventions: int,
        confidence: float,
        metrics: PredictiveMetrics | None,
    ) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        accepted = True
        if train_count < self.policy.minimum_train_samples:
            accepted = False
            reasons.append("training sample count below threshold")
        if effective_n < self.policy.minimum_effective_sample_size:
            accepted = False
            reasons.append("effective sample size below threshold")
        if parent_interventions < self.policy.minimum_interventional_parent_samples:
            accepted = False
            reasons.append("insufficient direct parent interventions for causal promotion")
        if confidence < self.policy.minimum_confidence:
            accepted = False
            reasons.append("posterior confidence below threshold")
        if metrics is not None:
            if metrics.log_loss > self.policy.maximum_log_loss:
                accepted = False
                reasons.append("holdout log loss exceeds threshold")
            if metrics.brier_score > self.policy.maximum_brier_score:
                accepted = False
                reasons.append("holdout Brier score exceeds threshold")
            if metrics.expected_calibration_error > self.policy.maximum_ece:
                accepted = False
                reasons.append("holdout calibration error exceeds threshold")
        if accepted:
            reasons.append("mechanism passed Bayesian interventional promotion gate")
        return accepted, tuple(reasons)

    def local_bdeu_score(
        self,
        child_id: str,
        parent_ids: Sequence[str],
        samples: Sequence[TransitionSample],
        *,
        regime: str = "default",
    ) -> LocalStructureScore:
        child = self.model.variable(child_id)
        parents = tuple(parent_ids)
        parent_domains = {parent: self.model.variable(parent).domain for parent in parents}
        resolved: list[_ResolvedSample] = []
        child_exclusions = interventional = observational = 0
        for sample in samples:
            if sample.regime != regime or not sample.verified:
                continue
            if child_id in sample.interventions:
                child_exclusions += 1
                continue
            item = self.resolver.resolve(
                sample,
                child_id=child_id,
                parent_ids=parents,
                child_domain=child.domain,
                parent_domains=parent_domains,
            )
            if item is None:
                continue
            resolved.append(item)
            if item.parent_intervened:
                interventional += 1
            else:
                observational += 1
        q = 1
        for parent in parents:
            q *= len(parent_domains[parent])
        r = len(child.domain)
        alpha_ij = self.policy.equivalent_sample_size / max(1, q)
        alpha_ijk = self.policy.equivalent_sample_size / max(1, q * r)
        counts: defaultdict[tuple[tuple[str, str], ...], Counter[str]] = defaultdict(Counter)
        for item in resolved:
            counts[item.parent_assignment][item.child_value] += item.sample.weight
        score = 0.0
        for row_counts in counts.values():
            n_ij = sum(row_counts.values())
            score += math.lgamma(alpha_ij) - math.lgamma(alpha_ij + n_ij)
            for value in child.domain:
                n_ijk = row_counts.get(value, 0.0)
                score += math.lgamma(alpha_ijk + n_ijk) - math.lgamma(alpha_ijk)
        parameter_count = max(0, q * (r - 1))
        fp = stable_fingerprint(
            {
                "child": child_id,
                "parents": parents,
                "score": score,
                "parameters": parameter_count,
                "usable": len(resolved),
            }
        )
        return LocalStructureScore(
            child_id=child_id,
            parent_ids=parents,
            bdeu_log_score=score,
            parameter_count=parameter_count,
            observed_parent_configurations=len(counts),
            usable_samples=len(resolved),
            interventional_parent_samples=interventional,
            observational_samples=observational,
            child_intervention_exclusions=child_exclusions,
            fingerprint=fp,
        )

    def compare_parent_sets(
        self,
        child_id: str,
        candidates: Sequence[Sequence[str]],
        samples: Sequence[TransitionSample],
        *,
        regime: str = "default",
    ) -> tuple[LocalStructureScore, ...]:
        scores = [
            self.local_bdeu_score(child_id, tuple(candidate), samples, regime=regime)
            for candidate in candidates
        ]
        scores.sort(
            key=lambda item: (
                item.bdeu_log_score,
                -item.parameter_count,
                item.interventional_parent_samples,
                item.parent_ids,
            ),
            reverse=True,
        )
        return tuple(scores)

    @staticmethod
    def _metrics_json(metrics: PredictiveMetrics | None) -> Any:
        if metrics is None:
            return None
        return {
            "count": metrics.count,
            "weighted_count": metrics.weighted_count,
            "log_loss": metrics.log_loss,
            "brier_score": metrics.brier_score,
            "ece": metrics.expected_calibration_error,
            "mce": metrics.maximum_calibration_error,
            "accuracy": metrics.accuracy,
        }


def promote_training_report(
    report: MechanismTrainingReport,
    *,
    current: CausalMechanism | None = None,
) -> CausalMechanism:
    """Convert a passed report into a learned mechanism; no store mutation."""
    if not isinstance(report, MechanismTrainingReport):
        raise TypeError("report must be MechanismTrainingReport")
    if not report.promotable:
        raise InterventionalLearningError("training report did not pass promotion gate")
    version = current.version + 1 if current is not None else report.mechanism.version
    return CausalMechanism(
        child_id=report.mechanism.child_id,
        parent_ids=report.mechanism.parent_ids,
        rows=report.mechanism.rows,
        fallback=report.mechanism.fallback,
        status=MechanismStatus.LEARNED,
        confidence=report.confidence,
        sample_count=report.mechanism.sample_count,
        regime=report.mechanism.regime,
        provenance=report.mechanism.provenance,
        version=version,
        metadata={**dict(report.mechanism.metadata), "training_report_id": report.report_id, "training_report_fingerprint": report.fingerprint},
    )
