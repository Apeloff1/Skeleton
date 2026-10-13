"""Human-review surface for AI shell proposals.

Review data is intentionally explicit and redacted. It never includes resolved
environment values or executable host paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.critic import CritiqueReport
from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


@dataclass(frozen=True)
class ReviewAction:
    action_id: str
    command: str
    args: tuple[str, ...]
    cwd: str | None
    environment_keys: tuple[str, ...]
    timeout_seconds: float | None
    effects: tuple[str, ...]
    reversible: bool
    compensation_command: str
    depends_on: tuple[str, ...]
    continue_on_failure: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "environment_keys": list(self.environment_keys),
            "timeout_seconds": self.timeout_seconds,
            "effects": list(self.effects),
            "reversible": self.reversible,
            "compensation_command": self.compensation_command,
            "depends_on": list(self.depends_on),
            "continue_on_failure": self.continue_on_failure,
        }


@dataclass(frozen=True)
class AIReviewView:
    intent_id: str
    goal: str
    proposal_id: str
    proposal_fingerprint: str
    model_id: str
    confidence: float
    uncertainty: float
    risk_score: int
    risk_band: str
    requires_approval: bool
    policy_reasons: tuple[str, ...]
    guardrail_findings: tuple[dict[str, str], ...]
    assumptions: tuple[str, ...]
    actions: tuple[ReviewAction, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "goal": self.goal,
            "proposal_id": self.proposal_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "model_id": self.model_id,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "requires_approval": self.requires_approval,
            "policy_reasons": list(self.policy_reasons),
            "guardrail_findings": list(self.guardrail_findings),
            "assumptions": list(self.assumptions),
            "actions": [item.to_dict() for item in self.actions],
        }


class AIReviewBuilder:
    def __init__(self, effects: EffectRegistry) -> None:
        self.effects = effects

    def build(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        critique: CritiqueReport,
    ) -> AIReviewView:
        actions = []
        for action in proposal.actions:
            contract = self.effects.inspect(action.command)
            effects = ()
            reversible = False
            compensation = ""
            if contract is not None:
                effects = tuple(sorted(item.value for item in contract.effects))
                reversible = contract.reversible
                compensation = contract.compensation_command
            actions.append(
                ReviewAction(
                    action.action_id,
                    action.command,
                    action.args,
                    action.cwd,
                    tuple(sorted(action.environment_refs)),
                    action.timeout_seconds,
                    effects,
                    reversible,
                    compensation,
                    tuple(sorted(action.depends_on)),
                    action.continue_on_failure,
                )
            )
        return AIReviewView(
            intent_id=intent.intent_id,
            goal=intent.goal,
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=proposal.fingerprint,
            model_id=proposal.model_id,
            confidence=proposal.confidence,
            uncertainty=proposal.uncertainty,
            risk_score=critique.risk.score,
            risk_band=critique.risk.band.value,
            requires_approval=critique.requires_approval,
            policy_reasons=critique.policy.reasons,
            guardrail_findings=tuple(
                item.to_dict() for item in critique.guardrails.findings
            ),
            assumptions=proposal.assumptions,
            actions=tuple(actions),
        )
