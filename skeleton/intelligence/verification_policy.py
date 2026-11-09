"""Deterministic risk-to-verification-level policy.

The selector is intentionally independent of model confidence. Risk, claim kind,
model-origin status, and action effect determine the minimum verification level.
Higher levels include the obligations of all lower levels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.contracts.verification import (
    ClaimKind,
    VerificationClaim,
    VerificationLevel,
    VerificationRisk,
)


class VerificationPolicyError(ValueError):
    """Verification policy input is invalid."""


@dataclass(frozen=True, slots=True)
class VerificationPolicyDecision:
    level: VerificationLevel
    required_modes: tuple[str, ...]
    min_independent_origins: int
    allow_model_only_evidence: bool
    require_postcondition: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", VerificationLevel(self.level))
        if (
            isinstance(self.min_independent_origins, bool)
            or not isinstance(self.min_independent_origins, int)
            or self.min_independent_origins < 0
        ):
            raise VerificationPolicyError(
                "min_independent_origins must be a non-negative integer"
            )
        if not isinstance(self.allow_model_only_evidence, bool):
            raise VerificationPolicyError(
                "allow_model_only_evidence must be boolean"
            )
        if not isinstance(self.require_postcondition, bool):
            raise VerificationPolicyError("require_postcondition must be boolean")

    def requires(self, level: VerificationLevel) -> bool:
        return self.level >= VerificationLevel(level)


_RISK_LEVEL = {
    VerificationRisk.LOW: VerificationLevel.STRUCTURAL,
    VerificationRisk.MEDIUM: VerificationLevel.EVIDENCE,
    VerificationRisk.HIGH: VerificationLevel.INDEPENDENT,
    VerificationRisk.CRITICAL: VerificationLevel.POSTCONDITION,
}

_ACTION_EFFECT_LEVEL = {
    "read_only": VerificationLevel.EVIDENCE,
    "reversible": VerificationLevel.INDEPENDENT,
    "irreversible": VerificationLevel.POSTCONDITION,
}


def _max_level(levels: Iterable[VerificationLevel]) -> VerificationLevel:
    return max(
        (VerificationLevel(level) for level in levels),
        default=VerificationLevel.STRUCTURAL,
    )


def select_verification_policy(
    claim: VerificationClaim,
    *,
    action_effect: str | None = None,
    externally_observable_action: bool = False,
) -> VerificationPolicyDecision:
    """Select the minimum verification strength for one canonical claim.

    action_effect accepts the canonical tool-effect values read_only,
    reversible or irreversible. Model confidence is not an input and cannot
    weaken this decision.
    """

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    normalized_effect: str | None = None
    if action_effect is not None:
        if not isinstance(action_effect, str) or not action_effect.strip():
            raise VerificationPolicyError("action_effect must be non-empty")
        normalized_effect = action_effect.strip().lower()
        if normalized_effect not in _ACTION_EFFECT_LEVEL:
            raise VerificationPolicyError("action_effect is unsupported")
    if not isinstance(externally_observable_action, bool):
        raise VerificationPolicyError(
            "externally_observable_action must be boolean"
        )

    levels = [_RISK_LEVEL[claim.risk]]
    reasons = [f"risk:{claim.risk.value}"]

    if claim.generated_by_model and claim.kind in {
        ClaimKind.FACT,
        ClaimKind.INTERPRETATION,
        ClaimKind.STRUCTURED_OUTPUT,
        ClaimKind.TOOL_RESULT,
        ClaimKind.ACTION_OUTCOME,
    }:
        levels.append(VerificationLevel.EVIDENCE)
        reasons.append("model_origin_requires_external_evidence")

    if claim.kind is ClaimKind.TOOL_RESULT:
        levels.append(VerificationLevel.EVIDENCE)
        reasons.append("tool_result_requires_observation_evidence")

    if claim.kind is ClaimKind.ACTION_OUTCOME:
        levels.append(VerificationLevel.POSTCONDITION)
        reasons.append("action_outcome_requires_postcondition")

    if normalized_effect is not None:
        levels.append(_ACTION_EFFECT_LEVEL[normalized_effect])
        reasons.append("action_effect:" + normalized_effect)

    if externally_observable_action:
        levels.append(VerificationLevel.POSTCONDITION)
        reasons.append("external_action_requires_postcondition")

    level = _max_level(levels)
    if level is VerificationLevel.STRUCTURAL:
        modes = ("structural",)
        independent_origins = 0
    elif level is VerificationLevel.EVIDENCE:
        modes = ("structural", "evidence")
        independent_origins = 1
    elif level is VerificationLevel.INDEPENDENT:
        modes = ("structural", "evidence", "independent")
        independent_origins = 2
    else:
        modes = ("structural", "evidence", "independent", "postcondition")
        independent_origins = 2

    return VerificationPolicyDecision(
        level=level,
        required_modes=modes,
        min_independent_origins=independent_origins,
        allow_model_only_evidence=False,
        require_postcondition=level >= VerificationLevel.POSTCONDITION,
        reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "VerificationPolicyDecision",
    "VerificationPolicyError",
    "select_verification_policy",
]
