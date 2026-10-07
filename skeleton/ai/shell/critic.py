"""Deterministic and optional model-assisted critique of AI shell proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from skeleton.shells.ai.effects import EffectKind, EffectRegistry
from skeleton.shells.ai.guardrails import GuardrailReport, ModelOutputGuard
from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.policy import AIPolicyDecision, AIShellPolicy
from skeleton.shells.ai.protocol import AIModelRequest, AIModelResponse
from skeleton.shells.ai.risk import AIRiskAssessor, RiskAssessment
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class CritiqueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CritiqueFinding:
    severity: CritiqueSeverity
    code: str
    message: str
    source: str = "deterministic"

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True)
class CritiqueReport:
    guardrails: GuardrailReport
    risk: RiskAssessment
    policy: AIPolicyDecision
    findings: tuple[CritiqueFinding, ...]
    model_critique: Mapping[str, object]

    @property
    def accepted_for_execution(self) -> bool:
        return self.guardrails.ok and self.policy.allowed and not any(
            item.severity is CritiqueSeverity.ERROR for item in self.findings
        )

    @property
    def requires_approval(self) -> bool:
        return self.policy.requires_approval

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_for_execution": self.accepted_for_execution,
            "requires_approval": self.requires_approval,
            "guardrails": self.guardrails.to_dict(),
            "risk": self.risk.to_dict(),
            "policy": self.policy.to_dict(),
            "findings": [item.to_dict() for item in self.findings],
            "model_critique": dict(self.model_critique),
        }


class AIPlanCritic:
    """Criticism is advisory unless backed by deterministic checks.

    Model critique may add warnings, but cannot override guardrails, risk, or
    autonomy policy.
    """

    def __init__(
        self,
        effects: EffectRegistry,
        policy: AIShellPolicy,
        *,
        guard: ModelOutputGuard | None = None,
        model: AIModelPort | None = None,
    ) -> None:
        self.effects = effects
        self.policy = policy
        self.guard = guard or ModelOutputGuard()
        self.model = model
        self.risk_assessor = AIRiskAssessor(effects)

    def _effects(self, proposal: AIPlanProposal) -> frozenset[EffectKind]:
        result: set[EffectKind] = set()
        for action in proposal.actions:
            contract = self.effects.inspect(action.command)
            if contract is not None:
                result.update(contract.effects)
        return frozenset(result)

    def critique(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        *,
        request: AIModelRequest | None = None,
        response: AIModelResponse | None = None,
    ) -> CritiqueReport:
        guardrails = self.guard.inspect(intent, proposal)
        risk = self.risk_assessor.assess(intent, proposal)
        policy = self.policy.evaluate(
            intent,
            proposal,
            risk,
            proposal_effects=self._effects(proposal),
        )
        findings: list[CritiqueFinding] = []
        for reason in risk.reasons:
            findings.append(
                CritiqueFinding(CritiqueSeverity.WARNING, "risk_reason", reason)
            )
        for command in risk.unknown_commands:
            findings.append(
                CritiqueFinding(
                    CritiqueSeverity.ERROR,
                    "unknown_effect_contract",
                    f"command {command!r} has no effect declaration",
                )
            )
        if not guardrails.ok:
            findings.append(
                CritiqueFinding(
                    CritiqueSeverity.ERROR,
                    "guardrail_failure",
                    "deterministic model-output guardrails rejected proposal",
                )
            )
        if not policy.allowed and not policy.requires_approval:
            findings.append(
                CritiqueFinding(
                    CritiqueSeverity.ERROR,
                    "policy_denial",
                    "; ".join(policy.reasons) or "AI policy denied proposal",
                )
            )

        model_critique: Mapping[str, object] = {}
        if self.model is not None and request is not None and response is not None:
            raw = self.model.critique(request, response)
            model_critique = dict(raw)
            verdict = str(raw.get("verdict", "")).lower()
            if verdict in {"reject", "unsafe"}:
                findings.append(
                    CritiqueFinding(
                        CritiqueSeverity.WARNING,
                        "model_critic_reject",
                        "auxiliary model critic flagged the proposal",
                        source="model",
                    )
                )
        return CritiqueReport(
            guardrails,
            risk,
            policy,
            tuple(findings),
            model_critique,
        )
