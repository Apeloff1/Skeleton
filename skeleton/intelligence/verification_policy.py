"""Deterministic risk-to-verification-level policy.

The policy selects required assurance from objective risk characteristics.
Model self-confidence is intentionally absent: generated confidence can never
lower evidence, independence, freshness, or postcondition requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.contracts.verification import (
    ClaimKind,
    ProvenanceOrigin,
    VerificationLevel,
)


VERIFICATION_POLICY_VERSION = "verification-policy-v1"


class VerificationRiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_LEVEL_RANK = {
    VerificationLevel.STRUCTURAL: 0,
    VerificationLevel.GROUNDED: 1,
    VerificationLevel.INDEPENDENT: 2,
    VerificationLevel.HIGH_ASSURANCE: 3,
}


def _at_least(
    current: VerificationLevel,
    required: VerificationLevel,
) -> VerificationLevel:
    return (
        required
        if _LEVEL_RANK[required] > _LEVEL_RANK[current]
        else current
    )


@dataclass(frozen=True, slots=True)
class VerificationRiskProfile:
    risk_class: VerificationRiskClass
    claim_kind: ClaimKind
    claim_origin: ProvenanceOrigin
    external_side_effect: bool = False
    irreversible: bool = False
    security_sensitive: bool = False
    freshness_sensitive: bool = False
    scope_sensitive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "risk_class",
            VerificationRiskClass(self.risk_class),
        )
        object.__setattr__(self, "claim_kind", ClaimKind(self.claim_kind))
        object.__setattr__(
            self,
            "claim_origin",
            ProvenanceOrigin(self.claim_origin),
        )
        for field in (
            "external_side_effect",
            "irreversible",
            "security_sensitive",
            "freshness_sensitive",
            "scope_sensitive",
        ):
            if not isinstance(getattr(self, field), bool):
                raise TypeError(f"{field} must be boolean")


@dataclass(frozen=True, slots=True)
class VerificationRequirement:
    level: VerificationLevel
    min_independent_origins: int
    require_postcondition: bool
    require_fresh_evidence: bool
    require_scope_match: bool
    reasons: tuple[str, ...]
    policy_version: str = VERIFICATION_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", VerificationLevel(self.level))
        if (
            isinstance(self.min_independent_origins, bool)
            or not isinstance(self.min_independent_origins, int)
            or self.min_independent_origins < 0
            or self.min_independent_origins > 8
        ):
            raise ValueError("min_independent_origins must be within [0, 8]")
        for field in (
            "require_postcondition",
            "require_fresh_evidence",
            "require_scope_match",
        ):
            if not isinstance(getattr(self, field), bool):
                raise TypeError(f"{field} must be boolean")
        if not self.reasons:
            raise ValueError("verification requirement requires at least one reason")


def select_verification_requirement(
    profile: VerificationRiskProfile,
) -> VerificationRequirement:
    """Select a deterministic minimum assurance requirement.

    This function chooses *requirements*, not a final disposition. Satisfying
    those requirements is the responsibility of the verification runtime.
    """

    if not isinstance(profile, VerificationRiskProfile):
        raise TypeError("profile must be VerificationRiskProfile")

    if profile.risk_class is VerificationRiskClass.LOW:
        level = VerificationLevel.STRUCTURAL
        origins = 0
    elif profile.risk_class is VerificationRiskClass.MEDIUM:
        level = VerificationLevel.GROUNDED
        origins = 1
    elif profile.risk_class is VerificationRiskClass.HIGH:
        level = VerificationLevel.INDEPENDENT
        origins = 2
    else:
        level = VerificationLevel.HIGH_ASSURANCE
        origins = 2

    reasons = ["risk:" + profile.risk_class.value]
    require_postcondition = False
    require_fresh_evidence = False
    require_scope_match = False

    # A model-authored factual assertion cannot self-verify from its own text or
    # confidence. Even low-risk model facts require external grounding.
    if (
        profile.claim_origin is ProvenanceOrigin.MODEL
        and profile.claim_kind
        in {ClaimKind.FACT, ClaimKind.INFERENCE, ClaimKind.ACTION_OUTCOME}
    ):
        level = _at_least(level, VerificationLevel.GROUNDED)
        origins = max(origins, 1)
        reasons.append("model_origin_requires_external_grounding")

    if profile.external_side_effect:
        level = _at_least(level, VerificationLevel.INDEPENDENT)
        origins = max(origins, 1)
        require_postcondition = True
        reasons.append("external_side_effect_requires_postcondition")

    if profile.irreversible:
        level = _at_least(level, VerificationLevel.HIGH_ASSURANCE)
        origins = max(origins, 2)
        require_postcondition = True
        reasons.append("irreversible_action_requires_high_assurance")

    if profile.security_sensitive:
        level = _at_least(level, VerificationLevel.HIGH_ASSURANCE)
        origins = max(origins, 2)
        reasons.append("security_sensitive_requires_high_assurance")

    if profile.freshness_sensitive:
        level = _at_least(level, VerificationLevel.GROUNDED)
        origins = max(origins, 1)
        require_fresh_evidence = True
        reasons.append("freshness_sensitive_requires_current_evidence")

    if profile.scope_sensitive:
        level = _at_least(level, VerificationLevel.GROUNDED)
        origins = max(origins, 1)
        require_scope_match = True
        reasons.append("scope_sensitive_requires_scope_match")

    if profile.claim_kind is ClaimKind.ACTION_OUTCOME:
        require_postcondition = True
        level = _at_least(level, VerificationLevel.GROUNDED)
        reasons.append("action_outcome_requires_postcondition")

    return VerificationRequirement(
        level=level,
        min_independent_origins=origins,
        require_postcondition=require_postcondition,
        require_fresh_evidence=require_fresh_evidence,
        require_scope_match=require_scope_match,
        reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "VERIFICATION_POLICY_VERSION",
    "VerificationRequirement",
    "VerificationRiskClass",
    "VerificationRiskProfile",
    "select_verification_requirement",
]
