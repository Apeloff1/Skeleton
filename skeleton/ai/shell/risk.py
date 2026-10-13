"""Deterministic risk assessment for model-proposed shell plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.effects import EffectKind, EffectRegistry
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskDimension(str, Enum):
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    SECRETS = "secrets"
    PRIVILEGE = "privilege"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    COMPLEXITY = "complexity"
    UNCERTAINTY = "uncertainty"
    REVERSIBILITY = "reversibility"


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    band: RiskBand
    dimensions: dict[str, int]
    reasons: tuple[str, ...]
    unknown_commands: tuple[str, ...]
    reversible: bool

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("risk score must be between 0 and 100")

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "band": self.band.value,
            "dimensions": dict(self.dimensions),
            "reasons": list(self.reasons),
            "unknown_commands": list(self.unknown_commands),
            "reversible": self.reversible,
        }


_WEIGHTS = {
    EffectKind.READ_FILESYSTEM: (RiskDimension.FILESYSTEM, 4),
    EffectKind.WRITE_FILESYSTEM: (RiskDimension.FILESYSTEM, 16),
    EffectKind.DELETE_FILESYSTEM: (RiskDimension.DESTRUCTIVE, 30),
    EffectKind.NETWORK: (RiskDimension.NETWORK, 18),
    EffectKind.PROCESS_CONTROL: (RiskDimension.EXTERNAL, 12),
    EffectKind.PACKAGE_CHANGE: (RiskDimension.DESTRUCTIVE, 22),
    EffectKind.VCS_READ: (RiskDimension.FILESYSTEM, 3),
    EffectKind.VCS_WRITE: (RiskDimension.DESTRUCTIVE, 18),
    EffectKind.SECRET_ACCESS: (RiskDimension.SECRETS, 28),
    EffectKind.PRIVILEGED: (RiskDimension.PRIVILEGE, 35),
    EffectKind.DEPLOYMENT: (RiskDimension.EXTERNAL, 30),
    EffectKind.EXTERNAL_SIDE_EFFECT: (RiskDimension.EXTERNAL, 20),
}


class AIRiskAssessor:
    def __init__(self, effects: EffectRegistry) -> None:
        self.effects = effects

    @staticmethod
    def _band(score: int) -> RiskBand:
        if score >= 75:
            return RiskBand.CRITICAL
        if score >= 50:
            return RiskBand.HIGH
        if score >= 25:
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def assess(self, intent: AIIntent, proposal: AIPlanProposal) -> RiskAssessment:
        dimensions = {item.value: 0 for item in RiskDimension}
        reasons: list[str] = []
        unknown: list[str] = []
        reversible = True
        seen_effects: set[EffectKind] = set()

        for action in proposal.actions:
            contract = self.effects.inspect(action.command)
            if contract is None:
                unknown.append(action.command)
                dimensions[RiskDimension.UNCERTAINTY.value] += 20
                reversible = False
                continue
            seen_effects.update(contract.effects)
            reversible = reversible and contract.reversible
            for effect in contract.effects:
                dimension, weight = _WEIGHTS[effect]
                dimensions[dimension.value] += weight
            if contract.human_approval_recommended:
                dimensions[RiskDimension.UNCERTAINTY.value] += 5

        if len(proposal.actions) > 8:
            dimensions[RiskDimension.COMPLEXITY.value] += min(20, len(proposal.actions) - 8)
        if proposal.uncertainty > 0.25:
            dimensions[RiskDimension.UNCERTAINTY.value] += round(proposal.uncertainty * 25)
        if proposal.confidence < 0.75:
            dimensions[RiskDimension.UNCERTAINTY.value] += round((0.75 - proposal.confidence) * 30)
        if intent.constraint.require_reversible and not reversible:
            dimensions[RiskDimension.REVERSIBILITY.value] += 25
            reasons.append("intent requires reversible actions")
        if EffectKind.NETWORK in seen_effects and not intent.constraint.allow_network:
            dimensions[RiskDimension.NETWORK.value] += 30
            reasons.append("network effect conflicts with intent constraint")
        if (
            {EffectKind.WRITE_FILESYSTEM, EffectKind.VCS_WRITE} & seen_effects
            and not intent.constraint.allow_writes
        ):
            dimensions[RiskDimension.FILESYSTEM.value] += 30
            reasons.append("write effect conflicts with intent constraint")
        if any(
            effect in seen_effects
            for effect in {
                EffectKind.DELETE_FILESYSTEM,
                EffectKind.PACKAGE_CHANGE,
                EffectKind.DEPLOYMENT,
                EffectKind.PRIVILEGED,
            }
        ) and not intent.constraint.allow_destructive:
            dimensions[RiskDimension.DESTRUCTIVE.value] += 35
            reasons.append("destructive effect conflicts with intent constraint")
        if unknown:
            reasons.append("one or more commands have no declared effect contract")

        if not reversible:
            dimensions[RiskDimension.REVERSIBILITY.value] += 10
        score = min(
            100,
            sum(min(40, value) for value in dimensions.values()),
        )
        if reversible:
            score = max(0, score - 5)
        return RiskAssessment(
            score=score,
            band=self._band(score),
            dimensions=dimensions,
            reasons=tuple(reasons),
            unknown_commands=tuple(sorted(set(unknown))),
            reversible=reversible,
        )
