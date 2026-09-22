"""Repeated-trial evaluation for Jeeves frontier inference.

Frontier-style inference often improves by spending more test-time compute and
sampling multiple candidate trajectories. Single-run score comparisons cannot
measure that effect reliably. This module adds host-side repeated-trial metrics,
including the standard empirical pass@k estimator, while tracking the extra
model-call and token cost.

The evaluator is offline and observational. It does not mutate runtime policy.
"""

from __future__ import annotations

import math
import statistics
import threading
from dataclasses import dataclass
from typing import Sequence

from .evaluation import EvalResult
from .types import (
    AgentContractError,
    finite_number,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
)


@dataclass(frozen=True, slots=True)
class FrontierTrialObservation:
    case_id: str
    variant: str
    run_id: str
    passed: bool
    score: float
    model_calls: int
    estimated_tokens: int
    result_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        variant = str(self.variant).strip().casefold()
        if not variant:
            raise AgentContractError("variant must be non-empty")
        object.__setattr__(self, "variant", variant[:128])
        if not isinstance(self.passed, bool):
            raise AgentContractError("passed must be boolean")
        object.__setattr__(self, "score", probability("score", self.score))
        for name in ("model_calls", "estimated_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class FrontierPassAtKCase:
    case_id: str
    variant: str
    k: int
    trials: int
    successes: int
    pass_at_k: float
    mean_score: float
    mean_model_calls: float
    mean_estimated_tokens: float
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        variant = str(self.variant).strip().casefold()
        if not variant:
            raise AgentContractError("variant must be non-empty")
        object.__setattr__(self, "variant", variant[:128])
        object.__setattr__(self, "k", positive_int("k", self.k, maximum=10_000_000))
        object.__setattr__(
            self,
            "trials",
            positive_int("trials", self.trials, maximum=10_000_000),
        )
        if (
            isinstance(self.successes, bool)
            or not isinstance(self.successes, int)
            or self.successes < 0
            or self.successes > self.trials
        ):
            raise AgentContractError("successes must be in [0, trials]")
        object.__setattr__(self, "pass_at_k", probability("pass_at_k", self.pass_at_k))
        object.__setattr__(self, "mean_score", probability("mean_score", self.mean_score))
        for name in ("mean_model_calls", "mean_estimated_tokens"):
            value = finite_number(name, getattr(self, name))
            if value < 0.0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class FrontierTrialReport:
    variant: str
    k: int
    case_count: int
    trial_count: int
    success_count: int
    mean_pass_at_k: float
    mean_score: float
    mean_model_calls: float
    mean_estimated_tokens: float
    cases: tuple[FrontierPassAtKCase, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        variant = str(self.variant).strip().casefold()
        if not variant:
            raise AgentContractError("variant must be non-empty")
        object.__setattr__(self, "variant", variant[:128])
        object.__setattr__(self, "k", positive_int("k", self.k, maximum=10_000_000))
        for name in ("case_count", "trial_count", "success_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")
        if self.success_count > self.trial_count:
            raise AgentContractError("success_count cannot exceed trial_count")
        object.__setattr__(
            self,
            "mean_pass_at_k",
            probability("mean_pass_at_k", self.mean_pass_at_k),
        )
        object.__setattr__(self, "mean_score", probability("mean_score", self.mean_score))
        for name in ("mean_model_calls", "mean_estimated_tokens"):
            value = finite_number(name, getattr(self, name))
            if value < 0.0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if any(not isinstance(item, FrontierPassAtKCase) for item in self.cases):
            raise TypeError("cases must contain FrontierPassAtKCase")
        if len(self.cases) != self.case_count:
            raise AgentContractError("case_count does not match cases")


@dataclass(frozen=True, slots=True)
class FrontierTrialComparison:
    baseline_variant: str
    frontier_variant: str
    k: int
    matched_cases: int
    baseline_mean_pass_at_k: float
    frontier_mean_pass_at_k: float
    pass_at_k_delta: float
    baseline_mean_score: float
    frontier_mean_score: float
    mean_score_delta: float
    incremental_model_calls: float
    incremental_estimated_tokens: float
    regressed_cases: int
    regression_rate: float
    fingerprint: str

    def __post_init__(self) -> None:
        for name in ("baseline_variant", "frontier_variant"):
            value = str(getattr(self, name)).strip().casefold()
            if not value:
                raise AgentContractError(f"{name} must be non-empty")
            object.__setattr__(self, name, value[:128])
        object.__setattr__(self, "k", positive_int("k", self.k, maximum=10_000_000))
        for name in ("matched_cases", "regressed_cases"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")
        if self.regressed_cases > self.matched_cases:
            raise AgentContractError("regressed_cases cannot exceed matched_cases")
        for name in (
            "baseline_mean_pass_at_k",
            "frontier_mean_pass_at_k",
            "baseline_mean_score",
            "frontier_mean_score",
            "regression_rate",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in (
            "pass_at_k_delta",
            "mean_score_delta",
            "incremental_model_calls",
            "incremental_estimated_tokens",
        ):
            object.__setattr__(self, name, finite_number(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class FrontierTrialGate:
    passed: bool
    reasons: tuple[str, ...]
    comparison_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise AgentContractError("passed must be boolean")
        object.__setattr__(
            self,
            "reasons",
            tuple(
                str(reason).strip()[:2048]
                for reason in self.reasons
                if str(reason).strip()
            ),
        )


class FrontierTrialEvaluator:
    """Accumulate repeated eval runs and compare test-time-compute variants."""

    def __init__(self) -> None:
        self._observations: list[FrontierTrialObservation] = []
        self._lock = threading.RLock()

    def observe(
        self,
        result: EvalResult,
        *,
        variant: str,
        model_calls: int = 0,
        estimated_tokens: int = 0,
    ) -> FrontierTrialObservation:
        if not isinstance(result, EvalResult):
            raise TypeError("result must be EvalResult")
        if isinstance(model_calls, bool) or not isinstance(model_calls, int) or model_calls < 0:
            raise AgentContractError("model_calls must be a non-negative integer")
        if (
            isinstance(estimated_tokens, bool)
            or not isinstance(estimated_tokens, int)
            or estimated_tokens < 0
        ):
            raise AgentContractError("estimated_tokens must be a non-negative integer")
        payload = {
            "case": result.case_id,
            "variant": str(variant).strip().casefold(),
            "run": result.run_id,
            "passed": result.passed,
            "score": result.score,
            "model_calls": model_calls,
            "tokens": estimated_tokens,
            "result": result.result_fingerprint,
        }
        observation = FrontierTrialObservation(
            case_id=result.case_id,
            variant=str(variant),
            run_id=result.run_id,
            passed=result.passed,
            score=result.score,
            model_calls=model_calls,
            estimated_tokens=estimated_tokens,
            result_fingerprint=result.result_fingerprint,
            fingerprint=stable_fingerprint(payload),
        )
        with self._lock:
            self._observations.append(observation)
        return observation

    def observations(self) -> tuple[FrontierTrialObservation, ...]:
        with self._lock:
            return tuple(self._observations)

    @staticmethod
    def empirical_pass_at_k(*, trials: int, successes: int, k: int) -> float:
        n = positive_int("trials", trials, maximum=10_000_000)
        if isinstance(successes, bool) or not isinstance(successes, int):
            raise AgentContractError("successes must be an integer")
        if successes < 0 or successes > n:
            raise AgentContractError("successes must be in [0, trials]")
        requested_k = positive_int("k", k, maximum=10_000_000)
        effective_k = min(requested_k, n)
        if successes == 0:
            return 0.0
        failures = n - successes
        if failures < effective_k:
            return 1.0
        denominator = math.comb(n, effective_k)
        if denominator <= 0:
            return 0.0
        return 1.0 - math.comb(failures, effective_k) / denominator

    def report(self, *, variant: str, k: int = 1) -> FrontierTrialReport:
        normalized_variant = str(variant).strip().casefold()
        if not normalized_variant:
            raise AgentContractError("variant must be non-empty")
        k = positive_int("k", k, maximum=10_000_000)
        observations = tuple(
            item for item in self.observations() if item.variant == normalized_variant
        )
        grouped: dict[str, list[FrontierTrialObservation]] = {}
        for item in observations:
            grouped.setdefault(item.case_id, []).append(item)

        rows: list[FrontierPassAtKCase] = []
        for case_id in sorted(grouped):
            values = tuple(grouped[case_id])
            successes = sum(1 for item in values if item.passed)
            pass_at_k = self.empirical_pass_at_k(
                trials=len(values),
                successes=successes,
                k=k,
            )
            mean_score = statistics.fmean(item.score for item in values)
            mean_calls = statistics.fmean(item.model_calls for item in values)
            mean_tokens = statistics.fmean(item.estimated_tokens for item in values)
            fingerprint = stable_fingerprint(
                {
                    "case": case_id,
                    "variant": normalized_variant,
                    "k": k,
                    "trials": [item.fingerprint for item in values],
                    "pass_at_k": pass_at_k,
                    "mean_score": mean_score,
                    "mean_calls": mean_calls,
                    "mean_tokens": mean_tokens,
                }
            )
            rows.append(
                FrontierPassAtKCase(
                    case_id=case_id,
                    variant=normalized_variant,
                    k=k,
                    trials=len(values),
                    successes=successes,
                    pass_at_k=pass_at_k,
                    mean_score=mean_score,
                    mean_model_calls=mean_calls,
                    mean_estimated_tokens=mean_tokens,
                    fingerprint=fingerprint,
                )
            )

        mean_pass = statistics.fmean(row.pass_at_k for row in rows) if rows else 0.0
        mean_score = (
            statistics.fmean(item.score for item in observations) if observations else 0.0
        )
        mean_calls = (
            statistics.fmean(item.model_calls for item in observations)
            if observations
            else 0.0
        )
        mean_tokens = (
            statistics.fmean(item.estimated_tokens for item in observations)
            if observations
            else 0.0
        )
        payload = {
            "variant": normalized_variant,
            "k": k,
            "cases": [row.fingerprint for row in rows],
            "trials": [item.fingerprint for item in observations],
            "mean_pass_at_k": mean_pass,
            "mean_score": mean_score,
            "mean_calls": mean_calls,
            "mean_tokens": mean_tokens,
        }
        return FrontierTrialReport(
            variant=normalized_variant,
            k=k,
            case_count=len(rows),
            trial_count=len(observations),
            success_count=sum(1 for item in observations if item.passed),
            mean_pass_at_k=mean_pass,
            mean_score=mean_score,
            mean_model_calls=mean_calls,
            mean_estimated_tokens=mean_tokens,
            cases=tuple(rows),
            fingerprint=stable_fingerprint(payload),
        )

    def compare(
        self,
        *,
        baseline_variant: str = "baseline",
        frontier_variant: str = "frontier",
        k: int = 1,
    ) -> FrontierTrialComparison:
        baseline = self.report(variant=baseline_variant, k=k)
        frontier = self.report(variant=frontier_variant, k=k)
        baseline_by_case = {row.case_id: row for row in baseline.cases}
        frontier_by_case = {row.case_id: row for row in frontier.cases}
        matched_ids = tuple(sorted(set(baseline_by_case) & set(frontier_by_case)))
        baseline_rows = tuple(baseline_by_case[case_id] for case_id in matched_ids)
        frontier_rows = tuple(frontier_by_case[case_id] for case_id in matched_ids)
        baseline_pass = (
            statistics.fmean(row.pass_at_k for row in baseline_rows)
            if baseline_rows
            else 0.0
        )
        frontier_pass = (
            statistics.fmean(row.pass_at_k for row in frontier_rows)
            if frontier_rows
            else 0.0
        )
        baseline_score = (
            statistics.fmean(row.mean_score for row in baseline_rows)
            if baseline_rows
            else 0.0
        )
        frontier_score = (
            statistics.fmean(row.mean_score for row in frontier_rows)
            if frontier_rows
            else 0.0
        )
        baseline_calls = (
            statistics.fmean(row.mean_model_calls for row in baseline_rows)
            if baseline_rows
            else 0.0
        )
        frontier_calls = (
            statistics.fmean(row.mean_model_calls for row in frontier_rows)
            if frontier_rows
            else 0.0
        )
        baseline_tokens = (
            statistics.fmean(row.mean_estimated_tokens for row in baseline_rows)
            if baseline_rows
            else 0.0
        )
        frontier_tokens = (
            statistics.fmean(row.mean_estimated_tokens for row in frontier_rows)
            if frontier_rows
            else 0.0
        )
        regressed = sum(
            1
            for baseline_row, frontier_row in zip(baseline_rows, frontier_rows)
            if frontier_row.pass_at_k + 1e-12 < baseline_row.pass_at_k
        )
        regression_rate = regressed / len(matched_ids) if matched_ids else 0.0
        payload = {
            "baseline": baseline.fingerprint,
            "frontier": frontier.fingerprint,
            "k": k,
            "matched": matched_ids,
            "baseline_pass": baseline_pass,
            "frontier_pass": frontier_pass,
            "baseline_score": baseline_score,
            "frontier_score": frontier_score,
            "calls": frontier_calls - baseline_calls,
            "tokens": frontier_tokens - baseline_tokens,
            "regressed": regressed,
        }
        return FrontierTrialComparison(
            baseline_variant=baseline.variant,
            frontier_variant=frontier.variant,
            k=k,
            matched_cases=len(matched_ids),
            baseline_mean_pass_at_k=baseline_pass,
            frontier_mean_pass_at_k=frontier_pass,
            pass_at_k_delta=frontier_pass - baseline_pass,
            baseline_mean_score=baseline_score,
            frontier_mean_score=frontier_score,
            mean_score_delta=frontier_score - baseline_score,
            incremental_model_calls=frontier_calls - baseline_calls,
            incremental_estimated_tokens=frontier_tokens - baseline_tokens,
            regressed_cases=regressed,
            regression_rate=regression_rate,
            fingerprint=stable_fingerprint(payload),
        )

    def promotion_gate(
        self,
        comparison: FrontierTrialComparison,
        *,
        minimum_cases: int = 8,
        minimum_pass_at_k_delta: float = 0.0,
        minimum_mean_score_delta: float = -0.01,
        maximum_regression_rate: float = 0.20,
    ) -> FrontierTrialGate:
        if not isinstance(comparison, FrontierTrialComparison):
            raise TypeError("comparison must be FrontierTrialComparison")
        minimum_cases = positive_int("minimum_cases", minimum_cases, maximum=1_000_000)
        minimum_pass_delta = finite_number(
            "minimum_pass_at_k_delta",
            minimum_pass_at_k_delta,
        )
        minimum_score_delta = finite_number(
            "minimum_mean_score_delta",
            minimum_mean_score_delta,
        )
        maximum_regressions = probability(
            "maximum_regression_rate",
            maximum_regression_rate,
        )
        reasons: list[str] = []
        if comparison.matched_cases < minimum_cases:
            reasons.append(
                f"insufficient matched repeated-trial cases: "
                f"{comparison.matched_cases} < {minimum_cases}"
            )
        if comparison.pass_at_k_delta < minimum_pass_delta:
            reasons.append(
                f"pass@{comparison.k} delta below promotion floor: "
                f"{comparison.pass_at_k_delta:.6f} < {minimum_pass_delta:.6f}"
            )
        if comparison.mean_score_delta < minimum_score_delta:
            reasons.append(
                f"mean score delta below promotion floor: "
                f"{comparison.mean_score_delta:.6f} < {minimum_score_delta:.6f}"
            )
        if comparison.regression_rate > maximum_regressions:
            reasons.append(
                f"case regression rate above promotion ceiling: "
                f"{comparison.regression_rate:.6f} > {maximum_regressions:.6f}"
            )
        fingerprint = stable_fingerprint(
            {
                "comparison": comparison.fingerprint,
                "minimum_cases": minimum_cases,
                "minimum_pass_at_k_delta": minimum_pass_delta,
                "minimum_mean_score_delta": minimum_score_delta,
                "maximum_regression_rate": maximum_regressions,
                "reasons": reasons,
            }
        )
        return FrontierTrialGate(
            passed=not reasons,
            reasons=tuple(reasons),
            comparison_fingerprint=comparison.fingerprint,
            fingerprint=fingerprint,
        )


__all__ = [
    "FrontierPassAtKCase",
    "FrontierTrialComparison",
    "FrontierTrialEvaluator",
    "FrontierTrialGate",
    "FrontierTrialObservation",
    "FrontierTrialReport",
]
