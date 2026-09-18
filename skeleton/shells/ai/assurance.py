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
    require_release_bands: frozenset[RiskBand] = frozenset()
    require_preconditions_bands: frozenset[RiskBand] = frozenset()
    require_human_approval_bands: frozenset[RiskBand] = frozenset()

    def __post_init__(self) -> None:
        for name in ("low", "medium", "high", "critical"):
            object.__setattr__(
                self,
                name,
                AssuranceLevel(getattr(self, name)),
            )
        for name in (
            "require_release_bands",
            "require_preconditions_bands",
            "require_human_approval_bands",
        ):
            object.__setattr__(
                self,
                name,
                frozenset(RiskBand(item) for item in getattr(self, name)),
            )

    @classmethod
    def production(cls) -> "AIExecutionAssurancePolicy":
        """Strict profile for production AI-directed shell execution."""
        return cls(
            require_release_bands=frozenset(
                {RiskBand.MEDIUM, RiskBand.HIGH}
            ),
            require_preconditions_bands=frozenset({RiskBand.HIGH}),
            require_human_approval_bands=frozenset({RiskBand.HIGH}),
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
    release_verified: bool
    preconditions_verified: bool
    human_approved: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "required": self.required.value,
            "sealed": self.sealed,
            "sandboxed": self.sandboxed,
            "release_verified": self.release_verified,
            "preconditions_verified": self.preconditions_verified,
            "human_approved": self.human_approved,
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
        sandbox_verified: bool,
        backend_id: str = "",
        release_verified: bool = False,
        preconditions_verified: bool = False,
        human_approved: bool = False,
    ) -> AssuranceDecision:
        band = RiskBand(band)
        required = self.policy.for_band(band)
        sandboxed = bool(sandbox_verified)
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

        if (
            band in self.policy.require_release_bands
            and not release_verified
        ):
            reasons.append("risk band requires verified release evidence")
        if (
            band in self.policy.require_preconditions_bands
            and not preconditions_verified
        ):
            reasons.append("risk band requires verified execution preconditions")
        if (
            band in self.policy.require_human_approval_bands
            and not human_approved
        ):
            reasons.append("risk band requires human approval")

        return AssuranceDecision(
            not reasons,
            required,
            sealed,
            sandboxed,
            bool(release_verified),
            bool(preconditions_verified),
            bool(human_approved),
            tuple(reasons),
        )

    def require(
        self,
        band: RiskBand,
        *,
        sealed: bool,
        sandbox_verified: bool,
        backend_id: str = "",
        release_verified: bool = False,
        preconditions_verified: bool = False,
        human_approved: bool = False,
    ) -> AssuranceDecision:
        decision = self.inspect(
            band,
            sealed=sealed,
            sandbox_verified=sandbox_verified,
            backend_id=backend_id,
            release_verified=release_verified,
            preconditions_verified=preconditions_verified,
            human_approved=human_approved,
        )
        if not decision.allowed:
            raise RuntimeError("; ".join(decision.reasons))
        return decision
