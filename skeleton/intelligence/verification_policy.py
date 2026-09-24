"""Deterministic risk-to-verification-level policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from skeleton.contracts.verification import (
    RiskClass,
    VerificationLevel,
)


_LEVEL_RANK = {
    VerificationLevel.NONE: 0,
    VerificationLevel.STRUCTURAL: 1,
    VerificationLevel.EVIDENCE: 2,
    VerificationLevel.ACTION: 3,
    VerificationLevel.HIGH_IMPACT: 4,
}

_DEFAULT_RISK_LEVEL = {
    RiskClass.LOW: VerificationLevel.STRUCTURAL,
    RiskClass.MEDIUM: VerificationLevel.EVIDENCE,
    RiskClass.HIGH: VerificationLevel.ACTION,
    RiskClass.CRITICAL: VerificationLevel.HIGH_IMPACT,
}


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    risk_levels: dict[RiskClass, VerificationLevel] = field(
        default_factory=lambda: dict(_DEFAULT_RISK_LEVEL)
    )
    capability_minimums: dict[str, VerificationLevel] = field(default_factory=dict)
    side_effect_minimum: VerificationLevel = VerificationLevel.ACTION
    external_claim_minimum: VerificationLevel = VerificationLevel.EVIDENCE
    high_impact_minimum: VerificationLevel = VerificationLevel.HIGH_IMPACT

    def __post_init__(self) -> None:
        normalized_risk: dict[RiskClass, VerificationLevel] = {}
        for risk, level in self.risk_levels.items():
            normalized_risk[RiskClass(risk)] = VerificationLevel(level)
        missing = set(RiskClass) - set(normalized_risk)
        if missing:
            raise ValueError(
                "risk_levels must cover every RiskClass: "
                + ", ".join(sorted(item.value for item in missing))
            )
        object.__setattr__(self, "risk_levels", normalized_risk)

        normalized_caps: dict[str, VerificationLevel] = {}
        for raw_capability, raw_level in self.capability_minimums.items():
            capability = str(raw_capability).strip()
            if not capability:
                raise ValueError("capability minimum key must be non-empty")
            normalized_caps[capability] = VerificationLevel(raw_level)
        object.__setattr__(self, "capability_minimums", normalized_caps)
        object.__setattr__(
            self,
            "side_effect_minimum",
            VerificationLevel(self.side_effect_minimum),
        )
        object.__setattr__(
            self,
            "external_claim_minimum",
            VerificationLevel(self.external_claim_minimum),
        )
        object.__setattr__(
            self,
            "high_impact_minimum",
            VerificationLevel(self.high_impact_minimum),
        )

    @staticmethod
    def stricter(
        left: VerificationLevel,
        right: VerificationLevel,
    ) -> VerificationLevel:
        left = VerificationLevel(left)
        right = VerificationLevel(right)
        return left if _LEVEL_RANK[left] >= _LEVEL_RANK[right] else right

    def select_level(
        self,
        *,
        risk_class: RiskClass,
        capability: str,
        has_external_claims: bool = False,
        has_side_effects: bool = False,
        high_impact: bool = False,
        requested_minimum: VerificationLevel | None = None,
        model_self_confidence: float | None = None,
    ) -> VerificationLevel:
        """Select from policy facts; model self-confidence is non-authoritative."""

        del model_self_confidence
        risk = RiskClass(risk_class)
        capability_key = str(capability).strip()
        if not capability_key:
            raise ValueError("capability is required")

        selected = self.risk_levels[risk]
        capability_level = self.capability_minimums.get(capability_key)
        if capability_level is not None:
            selected = self.stricter(selected, capability_level)
        if has_external_claims:
            selected = self.stricter(
                selected,
                self.external_claim_minimum,
            )
        if has_side_effects:
            selected = self.stricter(
                selected,
                self.side_effect_minimum,
            )
        if high_impact:
            selected = self.stricter(
                selected,
                self.high_impact_minimum,
            )
        if requested_minimum is not None:
            selected = self.stricter(
                selected,
                VerificationLevel(requested_minimum),
            )
        return selected


__all__ = ["VerificationPolicy"]
