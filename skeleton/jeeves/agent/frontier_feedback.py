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
class FrontierFeedbackRecommendation:
    minimum_quality_delta: float
    minimum_choice_probability_delta: float
    maximum_entropy_delta: float
    reasons: tuple[str, ...]
    fingerprint: str


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

    def recommendation(self) -> FrontierFeedbackRecommendation:
        report = self.report()
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
                entropy_delta += 0.04
                reasons.append("extra inference is associated with higher verified success")
            elif report.observed_escalation_delta < -0.08:
                entropy_delta -= 0.04
                reasons.append("extra inference is associated with lower verified success")
        quality_delta = finite_number("minimum_quality_delta", quality_delta)
        choice_delta = finite_number("minimum_choice_probability_delta", choice_delta)
        entropy_delta = finite_number("maximum_entropy_delta", entropy_delta)
        fingerprint = stable_fingerprint(
            {
                "report": report.fingerprint,
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
        )


__all__ = [
    "FrontierFeedbackRecommendation",
    "FrontierFeedbackReport",
    "FrontierFeedbackSample",
    "FrontierReasoningFeedback",
]
