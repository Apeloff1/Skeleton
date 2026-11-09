"""Eval-gated policy proposals for Jeeves frontier reasoning.

This module converts observed frontier-reasoning feedback into a bounded policy
candidate for offline trial. It never mutates a live runtime. Promotion remains
host-controlled and requires a passing matched-evaluation gate.

Only inference-allocation thresholds may change here. Verification boundaries,
verifier lower bounds, and abstention behavior are intentionally immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .frontier_feedback import (
    FrontierEvalGate,
    FrontierFeedbackRecommendation,
    FrontierFeedbackReport,
)
from .frontier_reasoning import FrontierReasoningPolicy
from .frontier_trials import FrontierTrialGate
from .types import AgentContractError, json_safe, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class FrontierPolicyBounds:
    """Hard bounds for an offline frontier policy proposal."""

    minimum_absolute_quality_floor: float = 0.50
    minimum_absolute_quality_ceiling: float = 0.90
    minimum_choice_probability_floor: float = 0.34
    minimum_choice_probability_ceiling: float = 0.85
    maximum_normalized_entropy_floor: float = 0.40
    maximum_normalized_entropy_ceiling: float = 0.95
    maximum_single_update: float = 0.08

    def __post_init__(self) -> None:
        for name in (
            "minimum_absolute_quality_floor",
            "minimum_absolute_quality_ceiling",
            "minimum_choice_probability_floor",
            "minimum_choice_probability_ceiling",
            "maximum_normalized_entropy_floor",
            "maximum_normalized_entropy_ceiling",
            "maximum_single_update",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.minimum_absolute_quality_floor > self.minimum_absolute_quality_ceiling:
            raise AgentContractError("absolute-quality bounds are inverted")
        if self.minimum_choice_probability_floor > self.minimum_choice_probability_ceiling:
            raise AgentContractError("choice-probability bounds are inverted")
        if self.maximum_normalized_entropy_floor > self.maximum_normalized_entropy_ceiling:
            raise AgentContractError("entropy bounds are inverted")


@dataclass(frozen=True, slots=True)
class FrontierPolicyProposal:
    """Deterministic, host-reviewable policy candidate."""

    baseline_policy: FrontierReasoningPolicy
    proposed_policy: FrontierReasoningPolicy
    approved_for_trial: bool
    changed_fields: Mapping[str, tuple[float, float]]
    evaluation_gate_fingerprint: str
    recommendation_fingerprint: str
    reasons: tuple[str, ...]
    fingerprint: str
    feedback_report_fingerprint: str | None = None
    trial_gate_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.baseline_policy, FrontierReasoningPolicy):
            raise TypeError("baseline_policy must be FrontierReasoningPolicy")
        if not isinstance(self.proposed_policy, FrontierReasoningPolicy):
            raise TypeError("proposed_policy must be FrontierReasoningPolicy")
        if not isinstance(self.approved_for_trial, bool):
            raise TypeError("approved_for_trial must be bool")
        normalized: dict[str, tuple[float, float]] = {}
        for name, pair in dict(self.changed_fields).items():
            if (
                not isinstance(name, str)
                or not isinstance(pair, tuple)
                or len(pair) != 2
            ):
                raise AgentContractError("changed_fields must map names to (old, new)")
            normalized[name] = (float(pair[0]), float(pair[1]))
        object.__setattr__(self, "changed_fields", json_safe(normalized))
        object.__setattr__(
            self,
            "reasons",
            tuple(str(reason).strip()[:2048] for reason in self.reasons if str(reason).strip()),
        )


class FrontierPolicyTuner:
    """Build bounded offline policy candidates from verified feedback."""

    def __init__(self, bounds: FrontierPolicyBounds | None = None) -> None:
        self.bounds = bounds or FrontierPolicyBounds()

    @staticmethod
    def _clip(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _bounded_delta(self, delta: float) -> float:
        limit = self.bounds.maximum_single_update
        return max(-limit, min(limit, float(delta)))

    def propose(
        self,
        baseline: FrontierReasoningPolicy,
        recommendation: FrontierFeedbackRecommendation,
        evaluation_gate: FrontierEvalGate,
        trial_gate: FrontierTrialGate | None = None,
        feedback_report: FrontierFeedbackReport | None = None,
    ) -> FrontierPolicyProposal:
        if not isinstance(baseline, FrontierReasoningPolicy):
            raise TypeError("baseline must be FrontierReasoningPolicy")
        if not isinstance(recommendation, FrontierFeedbackRecommendation):
            raise TypeError("recommendation must be FrontierFeedbackRecommendation")
        if not isinstance(evaluation_gate, FrontierEvalGate):
            raise TypeError("evaluation_gate must be FrontierEvalGate")
        if trial_gate is not None and not isinstance(trial_gate, FrontierTrialGate):
            raise TypeError("trial_gate must be FrontierTrialGate or None")
        if feedback_report is not None and not isinstance(
            feedback_report,
            FrontierFeedbackReport,
        ):
            raise TypeError("feedback_report must be FrontierFeedbackReport or None")

        reasons = list(recommendation.reasons)
        requested_change = any(
            abs(value) > 0.0
            for value in (
                recommendation.minimum_quality_delta,
                recommendation.minimum_choice_probability_delta,
                recommendation.maximum_entropy_delta,
            )
        )
        feedback_sufficient = (
            recommendation.sample_count >= 12
            and bool(recommendation.feedback_report_fingerprint)
        )
        feedback_bound = (
            feedback_report is not None
            and recommendation.feedback_report_fingerprint
            == feedback_report.fingerprint
            and recommendation.sample_count == feedback_report.count
            and recommendation.direct_count == feedback_report.direct_count
            and recommendation.escalated_count == feedback_report.escalated_count
        )
        entropy_change_requested = abs(recommendation.maximum_entropy_delta) > 0.0
        trial_gate_sufficient = (
            not entropy_change_requested
            or (trial_gate is not None and trial_gate.passed)
        )
        if requested_change and not feedback_sufficient:
            reasons.append(
                "insufficient bound feedback for policy change: "
                f"samples={recommendation.sample_count}, required>=12"
            )
        if requested_change and feedback_sufficient and not feedback_bound:
            reasons.append(
                "policy change requires the authoritative feedback report "
                "matching recommendation fingerprint and subgroup counts"
            )
        if entropy_change_requested and trial_gate is None:
            reasons.append(
                "entropy tuning requires a repeated-trial pass@k promotion gate"
            )
        elif entropy_change_requested and not trial_gate.passed:
            reasons.extend(trial_gate.reasons)
        if (
            not evaluation_gate.passed
            or (requested_change and (not feedback_sufficient or not feedback_bound))
            or not trial_gate_sufficient
        ):
            reasons.extend(evaluation_gate.reasons)
            fingerprint = stable_fingerprint(
                {
                    "baseline": self._policy_payload(baseline),
                    "recommendation": recommendation.fingerprint,
                    "eval_gate": evaluation_gate.fingerprint,
                    "trial_gate": trial_gate.fingerprint if trial_gate else None,
                    "feedback_report": feedback_report.fingerprint if feedback_report else None,
                    "approved": False,
                    "changes": {},
                    "reasons": reasons,
                }
            )
            return FrontierPolicyProposal(
                baseline_policy=baseline,
                proposed_policy=baseline,
                approved_for_trial=False,
                changed_fields={},
                evaluation_gate_fingerprint=evaluation_gate.fingerprint,
                recommendation_fingerprint=recommendation.fingerprint,
                reasons=tuple(reasons),
                fingerprint=fingerprint,
                feedback_report_fingerprint=(
                    feedback_report.fingerprint if feedback_report else None
                ),
                trial_gate_fingerprint=trial_gate.fingerprint if trial_gate else None,
            )

        next_absolute = self._clip(
            baseline.minimum_absolute_quality
            + self._bounded_delta(recommendation.minimum_quality_delta),
            self.bounds.minimum_absolute_quality_floor,
            self.bounds.minimum_absolute_quality_ceiling,
        )
        next_choice = self._clip(
            baseline.minimum_choice_probability
            + self._bounded_delta(recommendation.minimum_choice_probability_delta),
            self.bounds.minimum_choice_probability_floor,
            self.bounds.minimum_choice_probability_ceiling,
        )
        next_entropy = self._clip(
            baseline.maximum_normalized_entropy
            + self._bounded_delta(recommendation.maximum_entropy_delta),
            self.bounds.maximum_normalized_entropy_floor,
            self.bounds.maximum_normalized_entropy_ceiling,
        )

        proposed = replace(
            baseline,
            minimum_absolute_quality=next_absolute,
            minimum_choice_probability=next_choice,
            maximum_normalized_entropy=next_entropy,
        )
        changes: dict[str, tuple[float, float]] = {}
        for name in (
            "minimum_absolute_quality",
            "minimum_choice_probability",
            "maximum_normalized_entropy",
        ):
            old = float(getattr(baseline, name))
            new = float(getattr(proposed, name))
            if old != new:
                changes[name] = (old, new)

        # Verification policy is not tunable through this feedback path.
        if (
            proposed.verification_required_at is not baseline.verification_required_at
            or proposed.minimum_verification_lower_bound
            != baseline.minimum_verification_lower_bound
            or proposed.block_on_verifier_abstention
            != baseline.block_on_verifier_abstention
        ):
            raise AgentContractError("frontier feedback cannot alter verification policy")

        approved = bool(changes)
        if not approved:
            reasons.append("no bounded threshold change is justified by current feedback")
        fingerprint = stable_fingerprint(
            {
                "baseline": self._policy_payload(baseline),
                "proposed": self._policy_payload(proposed),
                "recommendation": recommendation.fingerprint,
                "eval_gate": evaluation_gate.fingerprint,
                "trial_gate": trial_gate.fingerprint if trial_gate else None,
                "feedback_report": feedback_report.fingerprint if feedback_report else None,
                "approved": approved,
                "changes": changes,
                "reasons": reasons,
            }
        )
        return FrontierPolicyProposal(
            baseline_policy=baseline,
            proposed_policy=proposed,
            approved_for_trial=approved,
            changed_fields=changes,
            evaluation_gate_fingerprint=evaluation_gate.fingerprint,
            recommendation_fingerprint=recommendation.fingerprint,
            reasons=tuple(reasons),
            fingerprint=fingerprint,
            feedback_report_fingerprint=(
                feedback_report.fingerprint if feedback_report else None
            ),
            trial_gate_fingerprint=trial_gate.fingerprint if trial_gate else None,
        )

    @staticmethod
    def _policy_payload(policy: FrontierReasoningPolicy) -> dict[str, object]:
        return {
            "maximum_candidates": policy.maximum_candidates,
            "softmax_temperature": policy.softmax_temperature,
            "minimum_absolute_quality": policy.minimum_absolute_quality,
            "minimum_choice_probability": policy.minimum_choice_probability,
            "minimum_choice_margin": policy.minimum_choice_margin,
            "maximum_normalized_entropy": policy.maximum_normalized_entropy,
            "maximum_action_disagreement": policy.maximum_action_disagreement,
            "maximum_outcome_disagreement": policy.maximum_outcome_disagreement,
            "minimum_evidence_quality": policy.minimum_evidence_quality,
            "maximum_lens_sensitivity_width": policy.maximum_lens_sensitivity_width,
            "maximum_lens_conflict": policy.maximum_lens_conflict,
            "verification_required_at": policy.verification_required_at.value,
            "minimum_verification_lower_bound": policy.minimum_verification_lower_bound,
            "block_on_verifier_abstention": policy.block_on_verifier_abstention,
        }


__all__ = [
    "FrontierPolicyBounds",
    "FrontierPolicyProposal",
    "FrontierPolicyTuner",
]
