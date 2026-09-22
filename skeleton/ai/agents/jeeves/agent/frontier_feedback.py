"""Observed-outcome feedback for Jeeves frontier reasoning.

This is an evaluation surface, not an autonomous policy mutator. It records
whether frontier orchestration decisions were later verified as successful,
then reports calibration, commit precision, and the observed cost/outcome
difference between direct and escalated inference. Recommendations are advisory
and never rewrite runtime thresholds by themselves.
"""

from __future__ import annotations

import statistics
import threading
from collections import Counter, deque
from dataclasses import dataclass
from typing import Mapping, Sequence

from .evaluation import EvalResult
from .frontier_reasoning import FrontierReasoningDecision, InferenceDisposition
from .types import AgentContractError, finite_number, positive_int, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class FrontierFeedbackSample:
    decision_fingerprint: str
    disposition: InferenceDisposition
    selected_candidate_id: str | None
    confidence: float
    verified_success: bool
    escalation_rounds: int
    model_calls: int
    estimated_tokens: int
    causes: tuple[str, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        object.__setattr__(
            self,
            "escalation_rounds",
            positive_int("escalation_rounds", self.escalation_rounds + 1, maximum=10_001) - 1,
        )
        for name in ("model_calls", "estimated_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class FrontierFeedbackReport:
    count: int
    commit_count: int
    commit_success_rate: float
    direct_count: int
    direct_success_rate: float
    escalated_count: int
    escalated_success_rate: float
    observed_escalation_delta: float
    mean_confidence: float
    accuracy: float
    brier_score: float
    calibration_gap: float
    mean_model_calls: float
    mean_estimated_tokens: float
    cause_success_rates: Mapping[str, float]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FrontierComputeEfficiency:
    direct_count: int
    escalated_count: int
    direct_success_rate: float
    escalated_success_rate: float
    direct_mean_model_calls: float
    escalated_mean_model_calls: float
    direct_mean_estimated_tokens: float
    escalated_mean_estimated_tokens: float
    incremental_success_rate: float
    incremental_model_calls: float
    incremental_estimated_tokens: float
    success_gain_per_extra_model_call: float
    success_gain_per_1k_extra_tokens: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FrontierFeedbackRecommendation:
    minimum_quality_delta: float
    minimum_choice_probability_delta: float
    maximum_entropy_delta: float
    reasons: tuple[str, ...]
    fingerprint: str
    feedback_report_fingerprint: str = ""
    sample_count: int = 0
    direct_count: int = 0
    escalated_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            "minimum_quality_delta",
            "minimum_choice_probability_delta",
            "maximum_entropy_delta",
        ):
            object.__setattr__(self, name, finite_number(name, getattr(self, name)))
        for name in ("sample_count", "direct_count", "escalated_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")
        if self.direct_count + self.escalated_count > self.sample_count:
            raise AgentContractError("feedback subgroup counts exceed sample_count")
        object.__setattr__(
            self,
            "feedback_report_fingerprint",
            str(self.feedback_report_fingerprint).strip(),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(
                str(reason).strip()[:2048]
                for reason in self.reasons
                if str(reason).strip()
            ),
        )


class FrontierReasoningFeedback:
    def __init__(self, *, history_limit: int = 4096) -> None:
        self.history_limit = positive_int("history_limit", history_limit, maximum=1_000_000)
        self._samples: deque[FrontierFeedbackSample] = deque(maxlen=self.history_limit)
        self._lock = threading.RLock()

    def observe(
        self,
        decision: FrontierReasoningDecision,
        *,
        verified_success: bool,
        escalation_rounds: int = 0,
        model_calls: int = 0,
        estimated_tokens: int = 0,
    ) -> FrontierFeedbackSample:
        if not isinstance(decision, FrontierReasoningDecision):
            raise TypeError("decision must be FrontierReasoningDecision")
        if not isinstance(verified_success, bool):
            raise TypeError("verified_success must be bool")
        if isinstance(escalation_rounds, bool) or not isinstance(escalation_rounds, int) or escalation_rounds < 0:
            raise AgentContractError("escalation_rounds must be a non-negative integer")
        for name, value in (("model_calls", model_calls), ("estimated_tokens", estimated_tokens)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be a non-negative integer")
        lead = decision.assessments[0] if decision.assessments else None
        confidence = (
            max(0.0, min(1.0, lead.absolute_quality * lead.choice_probability))
            if lead is not None
            else 0.0
        )
        payload = {
            "decision": decision.fingerprint,
            "success": verified_success,
            "rounds": escalation_rounds,
            "model_calls": model_calls,
            "tokens": estimated_tokens,
            "confidence": confidence,
        }
        sample = FrontierFeedbackSample(
            decision_fingerprint=decision.fingerprint,
            disposition=decision.disposition,
            selected_candidate_id=decision.leading_candidate.candidate_id if decision.leading_candidate else None,
            confidence=confidence,
            verified_success=verified_success,
            escalation_rounds=escalation_rounds,
            model_calls=model_calls,
            estimated_tokens=estimated_tokens,
            causes=tuple(cause.value for cause in decision.causes),
            fingerprint=stable_fingerprint(payload),
        )
        with self._lock:
            self._samples.append(sample)
        return sample

    def samples(self) -> tuple[FrontierFeedbackSample, ...]:
        with self._lock:
            return tuple(self._samples)

    def report(self) -> FrontierFeedbackReport:
        samples = self.samples()
        if not samples:
            fingerprint = stable_fingerprint({"frontier_feedback": []})
            return FrontierFeedbackReport(
                0, 0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, fingerprint
            )

        def rate(values: Sequence[FrontierFeedbackSample]) -> float:
            return sum(1 for item in values if item.verified_success) / len(values) if values else 0.0

        commits = tuple(item for item in samples if item.disposition in {InferenceDisposition.COMMIT, InferenceDisposition.VERIFY})
        direct = tuple(item for item in samples if item.escalation_rounds == 0)
        escalated = tuple(item for item in samples if item.escalation_rounds > 0)
        accuracy = rate(samples)
        mean_confidence = statistics.fmean(item.confidence for item in samples)
        brier = statistics.fmean(
            (item.confidence - (1.0 if item.verified_success else 0.0)) ** 2
            for item in samples
        )
        cause_counts: Counter[str] = Counter()
        cause_success: Counter[str] = Counter()
        for item in samples:
            for cause in item.causes:
                cause_counts[cause] += 1
                if item.verified_success:
                    cause_success[cause] += 1
        cause_rates = {
            cause: cause_success[cause] / count
            for cause, count in sorted(cause_counts.items())
            if count
        }
        direct_rate = rate(direct)
        escalated_rate = rate(escalated)
        payload = {
            "samples": [item.fingerprint for item in samples],
            "accuracy": accuracy,
            "mean_confidence": mean_confidence,
            "brier": brier,
            "direct": direct_rate,
            "escalated": escalated_rate,
            "cause_rates": cause_rates,
        }
        return FrontierFeedbackReport(
            count=len(samples),
            commit_count=len(commits),
            commit_success_rate=rate(commits),
            direct_count=len(direct),
            direct_success_rate=direct_rate,
            escalated_count=len(escalated),
            escalated_success_rate=escalated_rate,
            observed_escalation_delta=escalated_rate - direct_rate if direct and escalated else 0.0,
            mean_confidence=mean_confidence,
            accuracy=accuracy,
            brier_score=brier,
            calibration_gap=abs(mean_confidence - accuracy),
            mean_model_calls=statistics.fmean(item.model_calls for item in samples),
            mean_estimated_tokens=statistics.fmean(item.estimated_tokens for item in samples),
            cause_success_rates=cause_rates,
            fingerprint=stable_fingerprint(payload),
        )

    def compute_efficiency(self) -> FrontierComputeEfficiency:
        samples = self.samples()
        direct = tuple(item for item in samples if item.escalation_rounds == 0)
        escalated = tuple(item for item in samples if item.escalation_rounds > 0)

        def rate(values: Sequence[FrontierFeedbackSample]) -> float:
            return (
                sum(1 for item in values if item.verified_success) / len(values)
                if values
                else 0.0
            )

        def mean(values: Sequence[FrontierFeedbackSample], attribute: str) -> float:
            return (
                statistics.fmean(float(getattr(item, attribute)) for item in values)
                if values
                else 0.0
            )

        direct_success = rate(direct)
        escalated_success = rate(escalated)
        direct_calls = mean(direct, "model_calls")
        escalated_calls = mean(escalated, "model_calls")
        direct_tokens = mean(direct, "estimated_tokens")
        escalated_tokens = mean(escalated, "estimated_tokens")
        success_delta = (
            escalated_success - direct_success if direct and escalated else 0.0
        )
        call_delta = (
            escalated_calls - direct_calls if direct and escalated else 0.0
        )
        token_delta = (
            escalated_tokens - direct_tokens if direct and escalated else 0.0
        )
        per_call = success_delta / call_delta if call_delta > 0.0 else 0.0
        per_1k_tokens = (
            success_delta / (token_delta / 1000.0) if token_delta > 0.0 else 0.0
        )
        payload = {
            "direct_count": len(direct),
            "escalated_count": len(escalated),
            "direct_success": direct_success,
            "escalated_success": escalated_success,
            "direct_calls": direct_calls,
            "escalated_calls": escalated_calls,
            "direct_tokens": direct_tokens,
            "escalated_tokens": escalated_tokens,
            "success_delta": success_delta,
            "call_delta": call_delta,
            "token_delta": token_delta,
            "per_call": per_call,
            "per_1k_tokens": per_1k_tokens,
        }
        return FrontierComputeEfficiency(
            direct_count=len(direct),
            escalated_count=len(escalated),
            direct_success_rate=direct_success,
            escalated_success_rate=escalated_success,
            direct_mean_model_calls=direct_calls,
            escalated_mean_model_calls=escalated_calls,
            direct_mean_estimated_tokens=direct_tokens,
            escalated_mean_estimated_tokens=escalated_tokens,
            incremental_success_rate=success_delta,
            incremental_model_calls=call_delta,
            incremental_estimated_tokens=token_delta,
            success_gain_per_extra_model_call=per_call,
            success_gain_per_1k_extra_tokens=per_1k_tokens,
            fingerprint=stable_fingerprint(payload),
        )

    def recommendation(self) -> FrontierFeedbackRecommendation:
        report = self.report()
        efficiency = self.compute_efficiency()
        quality_delta = 0.0
        choice_delta = 0.0
        entropy_delta = 0.0
        reasons: list[str] = []
        if report.count >= 12 and report.calibration_gap > 0.12 and report.mean_confidence > report.accuracy:
            quality_delta += 0.04
            choice_delta += 0.03
            reasons.append("observed frontier confidence is materially over-calibrated")
        if report.escalated_count >= 6 and report.direct_count >= 6:
            if report.observed_escalation_delta > 0.08:
                entropy_delta -= 0.04
                reasons.append(
                    "extra inference is associated with higher verified success; "
                    "lower the entropy ceiling to escalate earlier "
                    f"(gain/call={efficiency.success_gain_per_extra_model_call:.4f}, "
                    f"gain/1k_tokens={efficiency.success_gain_per_1k_extra_tokens:.4f})"
                )
            elif report.observed_escalation_delta < -0.08:
                entropy_delta += 0.04
                reasons.append(
                    "extra inference is associated with lower verified success; "
                    "raise the entropy ceiling to escalate less often"
                )
        quality_delta = finite_number("minimum_quality_delta", quality_delta)
        choice_delta = finite_number("minimum_choice_probability_delta", choice_delta)
        entropy_delta = finite_number("maximum_entropy_delta", entropy_delta)
        fingerprint = stable_fingerprint(
            {
                "report": report.fingerprint,
                "efficiency": efficiency.fingerprint,
                "quality": quality_delta,
                "choice": choice_delta,
                "entropy": entropy_delta,
                "reasons": reasons,
            }
        )
        return FrontierFeedbackRecommendation(
            minimum_quality_delta=quality_delta,
            minimum_choice_probability_delta=choice_delta,
            maximum_entropy_delta=entropy_delta,
            reasons=tuple(reasons),
            fingerprint=fingerprint,
            feedback_report_fingerprint=report.fingerprint,
            sample_count=report.count,
            direct_count=report.direct_count,
            escalated_count=report.escalated_count,
        )


@dataclass(frozen=True, slots=True)
class FrontierEvalComparison:
    case_id: str
    baseline_fingerprint: str
    frontier_fingerprint: str
    baseline_score: float
    frontier_score: float
    score_delta: float
    baseline_passed: bool
    frontier_passed: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FrontierEvalReport:
    count: int
    improved: int
    regressed: int
    unchanged: int
    pass_gains: int
    pass_losses: int
    mean_score_delta: float
    median_score_delta: float
    win_rate: float
    loss_rate: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FrontierEvalGate:
    passed: bool
    reasons: tuple[str, ...]
    report_fingerprint: str
    fingerprint: str


class FrontierEvalFeedback:
    """Case-matched offline evaluation feedback for frontier promotion decisions."""

    def __init__(self, *, history_limit: int = 4096) -> None:
        self.history_limit = positive_int("history_limit", history_limit, maximum=1_000_000)
        self._comparisons: deque[FrontierEvalComparison] = deque(maxlen=self.history_limit)
        self._lock = threading.RLock()

    def observe(self, baseline: EvalResult, frontier: EvalResult) -> FrontierEvalComparison:
        if not isinstance(baseline, EvalResult) or not isinstance(frontier, EvalResult):
            raise TypeError("baseline and frontier must be EvalResult")
        if baseline.case_id != frontier.case_id:
            raise AgentContractError("evaluation comparison requires matching case_id")
        delta = frontier.score - baseline.score
        fingerprint = stable_fingerprint(
            {
                "case": baseline.case_id,
                "baseline": baseline.result_fingerprint,
                "frontier": frontier.result_fingerprint,
                "delta": delta,
                "baseline_passed": baseline.passed,
                "frontier_passed": frontier.passed,
            }
        )
        comparison = FrontierEvalComparison(
            case_id=baseline.case_id,
            baseline_fingerprint=baseline.result_fingerprint,
            frontier_fingerprint=frontier.result_fingerprint,
            baseline_score=baseline.score,
            frontier_score=frontier.score,
            score_delta=delta,
            baseline_passed=baseline.passed,
            frontier_passed=frontier.passed,
            fingerprint=fingerprint,
        )
        with self._lock:
            self._comparisons.append(comparison)
        return comparison

    def comparisons(self) -> tuple[FrontierEvalComparison, ...]:
        with self._lock:
            return tuple(self._comparisons)

    def report(self) -> FrontierEvalReport:
        comparisons = self.comparisons()
        if not comparisons:
            fingerprint = stable_fingerprint({"frontier_eval": []})
            return FrontierEvalReport(0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, fingerprint)
        epsilon = 1e-12
        improved = sum(1 for item in comparisons if item.score_delta > epsilon)
        regressed = sum(1 for item in comparisons if item.score_delta < -epsilon)
        unchanged = len(comparisons) - improved - regressed
        pass_gains = sum(
            1 for item in comparisons if not item.baseline_passed and item.frontier_passed
        )
        pass_losses = sum(
            1 for item in comparisons if item.baseline_passed and not item.frontier_passed
        )
        deltas = [item.score_delta for item in comparisons]
        payload = {
            "comparisons": [item.fingerprint for item in comparisons],
            "improved": improved,
            "regressed": regressed,
            "pass_gains": pass_gains,
            "pass_losses": pass_losses,
            "mean": statistics.fmean(deltas),
            "median": statistics.median(deltas),
        }
        return FrontierEvalReport(
            count=len(comparisons),
            improved=improved,
            regressed=regressed,
            unchanged=unchanged,
            pass_gains=pass_gains,
            pass_losses=pass_losses,
            mean_score_delta=statistics.fmean(deltas),
            median_score_delta=statistics.median(deltas),
            win_rate=improved / len(comparisons),
            loss_rate=regressed / len(comparisons),
            fingerprint=stable_fingerprint(payload),
        )

    def promotion_gate(
        self,
        *,
        minimum_cases: int = 8,
        minimum_mean_delta: float = 0.0,
        maximum_loss_rate: float = 0.20,
        allow_pass_losses: int = 0,
    ) -> FrontierEvalGate:
        minimum_cases = positive_int("minimum_cases", minimum_cases, maximum=1_000_000)
        mean_delta = finite_number("minimum_mean_delta", minimum_mean_delta)
        max_loss = probability("maximum_loss_rate", maximum_loss_rate)
        if isinstance(allow_pass_losses, bool) or not isinstance(allow_pass_losses, int) or allow_pass_losses < 0:
            raise AgentContractError("allow_pass_losses must be a non-negative integer")
        report = self.report()
        reasons: list[str] = []
        if report.count < minimum_cases:
            reasons.append(f"insufficient matched eval cases: {report.count} < {minimum_cases}")
        if report.mean_score_delta < mean_delta:
            reasons.append(
                f"mean score delta below promotion floor: {report.mean_score_delta:.6f} < {mean_delta:.6f}"
            )
        if report.loss_rate > max_loss:
            reasons.append(
                f"regression rate above promotion ceiling: {report.loss_rate:.6f} > {max_loss:.6f}"
            )
        if report.pass_losses > allow_pass_losses:
            reasons.append(
                f"pass-to-fail regressions exceed allowance: {report.pass_losses} > {allow_pass_losses}"
            )
        fingerprint = stable_fingerprint(
            {
                "report": report.fingerprint,
                "minimum_cases": minimum_cases,
                "minimum_mean_delta": mean_delta,
                "maximum_loss_rate": max_loss,
                "allow_pass_losses": allow_pass_losses,
                "reasons": reasons,
            }
        )
        return FrontierEvalGate(
            passed=not reasons,
            reasons=tuple(reasons),
            report_fingerprint=report.fingerprint,
            fingerprint=fingerprint,
        )


__all__ = [
    "FrontierComputeEfficiency",
    "FrontierEvalComparison",
    "FrontierEvalFeedback",
    "FrontierEvalGate",
    "FrontierEvalReport",
    "FrontierFeedbackRecommendation",
    "FrontierFeedbackReport",
    "FrontierFeedbackSample",
    "FrontierReasoningFeedback",
]
