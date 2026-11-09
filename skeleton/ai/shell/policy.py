"""AI autonomy policy layered above ordinary shell capability policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.effects import EffectKind
from skeleton.shells.ai.risk import RiskAssessment, RiskBand
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class AutonomyMode(str, Enum):
    OBSERVE = "observe"
    PROPOSE = "propose"
    LOW_RISK_AUTONOMOUS = "low_risk_autonomous"
    SUPERVISED = "supervised"


@dataclass(frozen=True)
class AIPolicyDecision:
    allowed: bool
    requires_approval: bool
    reasons: tuple[str, ...]
    risk_band: RiskBand

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reasons": list(self.reasons),
            "risk_band": self.risk_band.value,
        }


@dataclass(frozen=True)
class AIShellPolicy:
    autonomy: AutonomyMode = AutonomyMode.PROPOSE
    max_actions: int = 32
    min_confidence: float = 0.70
    max_uncertainty: float = 0.35
    auto_execute_bands: frozenset[RiskBand] = frozenset({RiskBand.LOW})
    approval_bands: frozenset[RiskBand] = frozenset(
        {RiskBand.MEDIUM, RiskBand.HIGH}
    )
    denied_effects: frozenset[EffectKind] = frozenset(
        {EffectKind.PRIVILEGED}
    )
    deny_unknown_effects: bool = True
    require_reversible_for_autonomy: bool = True

    def __post_init__(self) -> None:
        if self.max_actions <= 0 or self.max_actions > 1024:
            raise ValueError("max_actions out of range")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence out of range")
        if not 0.0 <= self.max_uncertainty <= 1.0:
            raise ValueError("max_uncertainty out of range")
        object.__setattr__(
            self,
            "auto_execute_bands",
            frozenset(RiskBand(item) for item in self.auto_execute_bands),
        )
        object.__setattr__(
            self,
            "approval_bands",
            frozenset(RiskBand(item) for item in self.approval_bands),
        )
        object.__setattr__(
            self,
            "denied_effects",
            frozenset(EffectKind(item) for item in self.denied_effects),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "autonomy": self.autonomy.value,
            "max_actions": self.max_actions,
            "min_confidence": self.min_confidence,
            "max_uncertainty": self.max_uncertainty,
            "auto_execute_bands": sorted(item.value for item in self.auto_execute_bands),
            "approval_bands": sorted(item.value for item in self.approval_bands),
            "denied_effects": sorted(item.value for item in self.denied_effects),
            "deny_unknown_effects": self.deny_unknown_effects,
            "require_reversible_for_autonomy": self.require_reversible_for_autonomy,
        }

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def evaluate(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        risk: RiskAssessment,
        *,
        proposal_effects: frozenset[EffectKind] = frozenset(),
    ) -> AIPolicyDecision:
        reasons: list[str] = []
        if len(proposal.actions) > min(self.max_actions, intent.constraint.max_steps):
            reasons.append("proposal exceeds action limit")
        if proposal.confidence < self.min_confidence:
            reasons.append("proposal confidence below policy threshold")
        if proposal.uncertainty > self.max_uncertainty:
            reasons.append("proposal uncertainty exceeds policy threshold")
        denied = proposal_effects & self.denied_effects
        if denied:
            reasons.append("proposal contains policy-denied effects")
        if self.deny_unknown_effects and risk.unknown_commands:
            reasons.append("proposal contains commands without effect contracts")
        if risk.band is RiskBand.CRITICAL:
            reasons.append("critical-risk proposals are not executable by AI policy")
        if reasons:
            return AIPolicyDecision(False, False, tuple(reasons), risk.band)

        if self.autonomy in {AutonomyMode.OBSERVE, AutonomyMode.PROPOSE}:
            return AIPolicyDecision(
                False,
                True,
                ("AI autonomy mode does not permit direct execution",),
                risk.band,
            )

        if risk.band in self.auto_execute_bands:
            if self.require_reversible_for_autonomy and not risk.reversible:
                return AIPolicyDecision(
                    False,
                    True,
                    ("autonomous execution requires reversible plan",),
                    risk.band,
                )
            return AIPolicyDecision(True, False, (), risk.band)

        if risk.band in self.approval_bands:
            return AIPolicyDecision(False, True, ("human approval required",), risk.band)

        return AIPolicyDecision(False, False, ("risk band is not permitted",), risk.band)
