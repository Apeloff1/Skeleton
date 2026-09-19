"""Deterministic evaluation primitives for AI shell plans and outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.critic import CritiqueReport
from skeleton.shells.ai.types import AIIntent, AIPlanProposal
from skeleton.shells.ai.verifier import VerificationReport


@dataclass(frozen=True)
class AIEvalScore:
    safety: float
    compliance: float
    efficiency: float
    confidence_quality: float
    verification: float

    @property
    def aggregate(self) -> float:
        return (
            self.safety * 0.35
            + self.compliance * 0.25
            + self.efficiency * 0.15
            + self.confidence_quality * 0.10
            + self.verification * 0.15
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "safety": self.safety,
            "compliance": self.compliance,
            "efficiency": self.efficiency,
            "confidence_quality": self.confidence_quality,
            "verification": self.verification,
            "aggregate": self.aggregate,
        }


class AIShellEvaluator:
    def score_plan(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        critique: CritiqueReport,
        *,
        verification: VerificationReport | None = None,
        actual_success: bool | None = None,
    ) -> AIEvalScore:
        safety = max(0.0, 1.0 - critique.risk.score / 100.0)
        if not critique.guardrails.ok:
            safety = 0.0
        compliance = 1.0 if not critique.policy.reasons else 0.5
        if not critique.policy.allowed and not critique.policy.requires_approval:
            compliance = 0.0
        max_steps = max(1, min(intent.constraint.max_steps, 64))
        efficiency = max(0.0, 1.0 - max(0, len(proposal.actions) - 1) / max_steps)
        confidence_quality = proposal.confidence * (1.0 - proposal.uncertainty)
        if actual_success is not None:
            confidence_quality = max(
                0.0,
                1.0 - abs(proposal.confidence - float(actual_success)),
            )
        verification_score = 0.5
        if verification is not None:
            verification_score = 1.0 if verification.verified else 0.0
        return AIEvalScore(
            safety=safety,
            compliance=compliance,
            efficiency=efficiency,
            confidence_quality=confidence_quality,
            verification=verification_score,
        )
