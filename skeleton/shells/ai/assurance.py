"""Execution-assurance requirements layered above ordinary AI policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.risk import RiskBand


class AssuranceLevel(str, Enum):
    STANDARD = "standard"
    SEALED = "sealed"
    SANDBOXED = "sandboxed"
    DENIED = "denied"


@dataclass(frozen=True)
class AIExecutionAssurancePolicy:
    low: AssuranceLevel = AssuranceLevel.STANDARD
    medium: AssuranceLevel = AssuranceLevel.SEALED
    high: AssuranceLevel = AssuranceLevel.SANDBOXED
    critical: AssuranceLevel = AssuranceLevel.DENIED

    def __post_init__(self) -> None:
        for name in ("low", "medium", "high", "critical"):
            object.__setattr__(
                self,
                name,
                AssuranceLevel(getattr(self, name)),
            )

    def for_band(self, band: RiskBand) -> AssuranceLevel:
        return {
            RiskBand.LOW: self.low,
            RiskBand.MEDIUM: self.medium,
            RiskBand.HIGH: self.high,
            RiskBand.CRITICAL: self.critical,
        }[RiskBand(band)]


@dataclass(frozen=True)
class AssuranceDecision:
    allowed: bool
    required: AssuranceLevel
    sealed: bool
    sandboxed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "required": self.required.value,
            "sealed": self.sealed,
            "sandboxed": self.sandboxed,
            "reasons": list(self.reasons),
        }


class AIExecutionAssuranceInspector:
    def __init__(
        self,
        policy: AIExecutionAssurancePolicy | None = None,
    ) -> None:
        self.policy = policy or AIExecutionAssurancePolicy()

    def inspect(
        self,
        band: RiskBand,
        *,
        sealed: bool,
        backend_id: str,
    ) -> AssuranceDecision:
        required = self.policy.for_band(band)
        sandboxed = backend_id.startswith("sandbox:")
        reasons = []
        if required is AssuranceLevel.DENIED:
            reasons.append("risk band is denied by execution assurance policy")
        elif required is AssuranceLevel.SEALED and not sealed:
            reasons.append("risk band requires sealed execution")
        elif required is AssuranceLevel.SANDBOXED:
            if not sealed:
                reasons.append("sandboxed risk band also requires sealed execution")
            if not sandboxed:
                reasons.append("risk band requires verified sandbox execution backend")
        return AssuranceDecision(
            not reasons,
            required,
            sealed,
            sandboxed,
            tuple(reasons),
        )

    def require(
        self,
        band: RiskBand,
        *,
        sealed: bool,
        backend_id: str,
    ) -> AssuranceDecision:
        decision = self.inspect(
            band,
            sealed=sealed,
            backend_id=backend_id,
        )
        if not decision.allowed:
            raise RuntimeError("; ".join(decision.reasons))
        return decision
