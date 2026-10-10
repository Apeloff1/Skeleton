"""Paired baseline/candidate evaluation for Mirror Room."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import NormalDist
from types import MappingProxyType
from typing import Mapping, Sequence

from skeleton.eval.experiment_registry import MetricDirection

from .contracts import (
    HardExample,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    ScenarioSplit,
    _digest,
)
from .sandbox import EpisodeReceipt, MirrorSandbox


@dataclass(frozen=True, slots=True)
class ScenarioComparison:
    """Paired evidence for one scenario under the exact same random seed."""

    scenario_id: str
    scenario_digest: str
    weight: float
    baseline_receipt: EpisodeReceipt
    candidate_receipt: EpisodeReceipt
    metric_deltas: Mapping[str, float]
    utility_delta: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_deltas",
            MappingProxyType(dict(self.metric_deltas)),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "scenario_id": self.scenario_id,
                "scenario_digest": self.scenario_digest,
                "weight": self.weight,
                "baseline_receipt": self.baseline_receipt.digest,
                "candidate_receipt": self.candidate_receipt.digest,
                "metric_deltas": dict(self.metric_deltas),
                "utility_delta": self.utility_delta,
            }
        )


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric_id: str
    direction: MetricDirection
    baseline_mean: float
    candidate_mean: float
    oriented_delta: float
    worst_case_delta: float
    lower_confidence_bound: float
    standard_error: float
    sample_count: int
    requested_confidence_level: float
    adjusted_confidence_level: float
    comparison_family_size: int
    passed: bool
    reason: str

    def payload(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "baseline_mean": self.baseline_mean,
            "candidate_mean": self.candidate_mean,
            "oriented_delta": self.oriented_delta,
            "worst_case_delta": self.worst_case_delta,
            "lower_confidence_bound": self.lower_confidence_bound,
            "standard_error": self.standard_error,
            "sample_count": self.sample_count,
            "requested_confidence_level": self.requested_confidence_level,
            "adjusted_confidence_level": self.adjusted_confidence_level,
            "comparison_family_size": self.comparison_family_size,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Immutable comparison report; positive utility always means improvement."""

    run_id: str
    split: ScenarioSplit
    baseline_candidate_id: str
    baseline_candidate_digest: str
    candidate_id: str
    candidate_digest: str
    scenario_comparisons: tuple[ScenarioComparison, ...]
    metric_comparisons: tuple[MetricComparison, ...]
    weighted_utility_delta: float
    passed: bool
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.production_authority is not False:
            raise MirrorRoomError("comparison report cannot carry production authority")
        if not self.scenario_comparisons:
            raise MirrorRoomError("comparison report requires scenario evidence")
        if not self.metric_comparisons:
            raise MirrorRoomError("comparison report requires metric evidence")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "run_id": self.run_id,
                "split": self.split.value,
                "baseline_candidate_id": self.baseline_candidate_id,
                "baseline_candidate_digest": self.baseline_candidate_digest,
                "candidate_id": self.candidate_id,
                "candidate_digest": self.candidate_digest,
                "scenario_comparisons": [
                    item.digest for item in self.scenario_comparisons
                ],
                "metric_comparisons": [
                    item.payload() for item in self.metric_comparisons
                ],
                "weighted_utility_delta": self.weighted_utility_delta,
                "passed": self.passed,
                "production_authority": False,
            }
        )

    def hard_examples(self, *, limit: int) -> tuple[HardExample, ...]:
        if self.split is not ScenarioSplit.TRAIN:
            raise MirrorRoomError("hard examples can be derived only from training data")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise MirrorRoomError("hard example limit must be positive")
        ordered = sorted(
            self.scenario_comparisons,
            key=lambda item: (item.utility_delta, item.scenario_id),
        )
        result = []
        for item in ordered[:limit]:
            # Low/negative utility is hard; absolute disagreement adds pressure
            # even when the candidate narrowly wins.
            difficulty = max(0.0, -item.utility_delta) + abs(item.utility_delta)
            result.append(
                HardExample(
                    scenario_id=item.scenario_id,
                    scenario_digest=item.scenario_digest,
                    difficulty=difficulty,
                    metric_deltas=item.metric_deltas,
                )
            )
        return tuple(result)


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total = sum(weights)
    if total <= 0.0:
        raise MirrorRoomError("comparison weights must be positive")
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / total


def _weighted_standard_error(
    values: Sequence[float],
    weights: Sequence[float],
    *,
    mean: float,
) -> float:
    if len(values) <= 1:
        return 0.0
    total_weight = sum(weights)
    squared_weight = sum(weight * weight for weight in weights)
    if total_weight <= 0.0 or squared_weight <= 0.0:
        return 0.0
    effective_n = (total_weight * total_weight) / squared_weight
    if effective_n <= 1.0:
        return 0.0
    variance = sum(
        weight * ((value - mean) ** 2)
        for value, weight in zip(values, weights, strict=True)
    ) / total_weight
    # Reliability-weighted population variance with effective sample size.
    return math.sqrt(max(0.0, variance) / effective_n)


def _oriented_delta(
    *,
    direction: MetricDirection,
    baseline: float,
    candidate: float,
) -> float:
    if direction is MetricDirection.MAXIMIZE:
        return candidate - baseline
    return baseline - candidate


class PairedEvaluator:
    """Run candidates and baselines on identical scenarios and seeds."""

    def __init__(self, spec: MirrorRoomSpec, sandbox: MirrorSandbox) -> None:
        if not isinstance(spec, MirrorRoomSpec):
            raise TypeError("spec must be MirrorRoomSpec")
        if not isinstance(sandbox, MirrorSandbox):
            raise TypeError("sandbox must be MirrorSandbox")
        if sandbox.spec.digest != spec.digest:
            raise MirrorRoomError("sandbox/spec identity mismatch")
        self.spec = spec
        self.sandbox = sandbox
        self._policies = {metric.metric_id: metric for metric in spec.metrics}
        self._manifest_metrics = {
            metric.metric_id: metric for metric in spec.manifest.metrics
        }

    def compare(
        self,
        *,
        run_id: str,
        baseline: MirrorCandidate,
        candidate: MirrorCandidate,
        scenarios: Sequence[MirrorScenario],
        split: ScenarioSplit,
        enforce_gate: bool = True,
        comparison_family_size: int = 1,
    ) -> ComparisonReport:
        try:
            expected_split = ScenarioSplit(split)
        except ValueError as exc:
            raise MirrorRoomError("invalid comparison split") from exc
        if baseline.candidate_id == candidate.candidate_id:
            raise MirrorRoomError("baseline and candidate must be distinct")
        if (
            isinstance(comparison_family_size, bool)
            or not isinstance(comparison_family_size, int)
            or comparison_family_size <= 0
        ):
            raise MirrorRoomError("comparison_family_size must be a positive integer")
        scenario_tuple = tuple(scenarios)
        if not scenario_tuple:
            raise MirrorRoomError("comparison requires scenarios")
        if any(item.split is not expected_split for item in scenario_tuple):
            raise MirrorRoomError("comparison received scenario from another split")
        ids = [item.scenario_id for item in scenario_tuple]
        if len(ids) != len(set(ids)):
            raise MirrorRoomError("comparison scenario IDs must be unique")

        minimum_samples = max(
            self._manifest_metrics[metric_id].minimum_samples
            for metric_id in self._policies
        )
        if enforce_gate and len(scenario_tuple) < minimum_samples:
            raise MirrorRoomError(
                f"{expected_split.value} split has fewer than required independent samples"
            )

        paired: list[ScenarioComparison] = []
        for scenario in sorted(scenario_tuple, key=lambda item: item.scenario_id):
            seed = self.sandbox.seed_for(run_id=run_id, scenario=scenario)
            baseline_receipt = self.sandbox.run_episode(
                run_id=run_id,
                candidate=baseline,
                scenario=scenario,
                seed=seed,
            )
            candidate_receipt = self.sandbox.run_episode(
                run_id=run_id,
                candidate=candidate,
                scenario=scenario,
                seed=seed,
            )
            deltas: dict[str, float] = {}
            utility = 0.0
            weight_total = 0.0
            for policy in self.spec.metrics:
                b = baseline_receipt.outcome.metric_values[policy.metric_id]
                c = candidate_receipt.outcome.metric_values[policy.metric_id]
                delta = _oriented_delta(
                    direction=policy.direction,
                    baseline=b,
                    candidate=c,
                )
                deltas[policy.metric_id] = delta
                utility += delta * policy.weight
                weight_total += policy.weight
            paired.append(
                ScenarioComparison(
                    scenario_id=scenario.scenario_id,
                    scenario_digest=scenario.digest,
                    weight=scenario.weight,
                    baseline_receipt=baseline_receipt,
                    candidate_receipt=candidate_receipt,
                    metric_deltas=dict(sorted(deltas.items())),
                    utility_delta=utility / weight_total,
                )
            )

        weights = [item.weight for item in paired]
        metric_reports: list[MetricComparison] = []
        useful_gain = False
        for policy in self.spec.metrics:
            baseline_values = [
                item.baseline_receipt.outcome.metric_values[policy.metric_id]
                for item in paired
            ]
            candidate_values = [
                item.candidate_receipt.outcome.metric_values[policy.metric_id]
                for item in paired
            ]
            deltas = [item.metric_deltas[policy.metric_id] for item in paired]
            baseline_mean = _weighted_mean(baseline_values, weights)
            candidate_mean = _weighted_mean(candidate_values, weights)
            mean_delta = _weighted_mean(deltas, weights)
            worst_case_delta = min(deltas)
            standard_error = _weighted_standard_error(
                deltas,
                weights,
                mean=mean_delta,
            )
            alpha = max(1e-12, 1.0 - policy.confidence_level)
            adjusted_confidence = min(
                1.0 - 1e-12,
                1.0 - (alpha / comparison_family_size),
            )
            z_score = NormalDist().inv_cdf(adjusted_confidence)
            lower_bound = mean_delta - z_score * standard_error

            if policy.guardrail:
                passed = (
                    mean_delta >= -policy.max_regression
                    and lower_bound >= -policy.max_regression
                    and worst_case_delta >= -policy.max_regression
                )
                reason = "guardrail_within_regression_budget" if passed else "guardrail_regression"
            else:
                threshold = policy.minimum_improvement
                passed = mean_delta >= threshold and lower_bound >= threshold
                reason = "confident_improvement" if passed else "insufficient_confident_gain"
                useful_gain = useful_gain or mean_delta > max(0.0, threshold)

            metric_reports.append(
                MetricComparison(
                    metric_id=policy.metric_id,
                    direction=policy.direction,
                    baseline_mean=baseline_mean,
                    candidate_mean=candidate_mean,
                    oriented_delta=mean_delta,
                    worst_case_delta=worst_case_delta,
                    lower_confidence_bound=lower_bound,
                    standard_error=standard_error,
                    sample_count=len(paired),
                    requested_confidence_level=policy.confidence_level,
                    adjusted_confidence_level=adjusted_confidence,
                    comparison_family_size=comparison_family_size,
                    passed=passed,
                    reason=reason,
                )
            )

        weighted_utility = _weighted_mean(
            [item.utility_delta for item in paired],
            weights,
        )
        gate_passed = all(item.passed for item in metric_reports) and useful_gain
        if not enforce_gate:
            gate_passed = weighted_utility > 0.0

        return ComparisonReport(
            run_id=run_id,
            split=expected_split,
            baseline_candidate_id=baseline.candidate_id,
            baseline_candidate_digest=baseline.digest,
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.digest,
            scenario_comparisons=tuple(paired),
            metric_comparisons=tuple(metric_reports),
            weighted_utility_delta=weighted_utility,
            passed=gate_passed,
        )


__all__ = [
    "ComparisonReport",
    "MetricComparison",
    "PairedEvaluator",
    "ScenarioComparison",
]
