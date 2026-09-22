"""Two-key evidence composition for Jeeves probabilistic governance.

This module composes point/distributional promotion evidence with stratified
uncertainty-calibration evidence.  It has no activation authority.  By default,
both child decisions must independently pass and the uncertainty evidence volume
must be commensurate with the point-forecast evidence volume.

The child decisions are integrity-checked before composition; their fingerprints
and the joint policy fingerprint are retained in the result so downstream code
can verify custody without trusting mutable booleans or detached metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .probabilistic_contracts import (
    ProbabilisticPromotionDecision,
    validate_probabilistic_promotion_decision,
)
from .probabilistic_governance import (
    ConformalGovernanceDecision,
    validate_conformal_governance_decision,
)
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class JointProbabilisticGovernanceGate:
    """Policy for composing independently validated evidence planes."""

    require_probabilistic_eligible: bool = True
    require_conformal_eligible: bool = True
    min_uncertainty_step_ratio: float = 0.50
    max_uncertainty_step_ratio: float = 1.50

    def __post_init__(self) -> None:
        if not isinstance(self.require_probabilistic_eligible, bool):
            raise StateSpaceError(
                "require_probabilistic_eligible must be a boolean",
                context={"reason": "invalid_joint_governance_gate"},
            )
        if not isinstance(self.require_conformal_eligible, bool):
            raise StateSpaceError(
                "require_conformal_eligible must be a boolean",
                context={"reason": "invalid_joint_governance_gate"},
            )
        minimum = _positive("min_uncertainty_step_ratio", self.min_uncertainty_step_ratio)
        maximum = _positive("max_uncertainty_step_ratio", self.max_uncertainty_step_ratio)
        if minimum > maximum:
            raise StateSpaceError(
                "min_uncertainty_step_ratio cannot exceed max_uncertainty_step_ratio",
                context={"reason": "invalid_joint_governance_gate"},
            )


@dataclass(frozen=True, slots=True)
class JointProbabilisticGovernanceDecision:
    """Integrity-bound joint evidence decision with no activation authority."""

    eligible: bool
    reasons: tuple[str, ...]
    probabilistic_eligible: bool
    conformal_eligible: bool
    probabilistic_folds: int
    conformal_scored_steps: int
    uncertainty_step_ratio: float
    probabilistic_decision_fingerprint: str
    conformal_decision_fingerprint: str
    gate_fingerprint: str
    fingerprint: str


def evaluate_joint_probabilistic_governance(
    probabilistic: ProbabilisticPromotionDecision,
    conformal: ConformalGovernanceDecision,
    *,
    gate: JointProbabilisticGovernanceGate | None = None,
) -> JointProbabilisticGovernanceDecision:
    """Compose two evidence decisions after independently verifying both."""

    actual_gate = gate or JointProbabilisticGovernanceGate()
    validate_probabilistic_promotion_decision(probabilistic)
    validate_conformal_governance_decision(conformal)

    ratio = conformal.scored_steps / probabilistic.folds
    reasons: list[str] = []
    if actual_gate.require_probabilistic_eligible and not probabilistic.eligible:
        reasons.append("probabilistic_evidence_plane_ineligible")
    if actual_gate.require_conformal_eligible and not conformal.eligible:
        reasons.append("conformal_evidence_plane_ineligible")
    if ratio < actual_gate.min_uncertainty_step_ratio:
        reasons.append("uncertainty_evidence_ratio_below_gate")
    if ratio > actual_gate.max_uncertainty_step_ratio:
        reasons.append("uncertainty_evidence_ratio_above_gate")

    eligible = not reasons
    if eligible:
        reasons.append("joint_probabilistic_evidence_gate_passed")

    gate_fingerprint = _gate_fingerprint(actual_gate)
    fingerprint = _decision_fingerprint(
        eligible=eligible,
        reasons=tuple(reasons),
        probabilistic_eligible=probabilistic.eligible,
        conformal_eligible=conformal.eligible,
        probabilistic_folds=probabilistic.folds,
        conformal_scored_steps=conformal.scored_steps,
        uncertainty_step_ratio=ratio,
        probabilistic_decision_fingerprint=probabilistic.fingerprint,
        conformal_decision_fingerprint=conformal.fingerprint,
        gate_fingerprint=gate_fingerprint,
    )
    return JointProbabilisticGovernanceDecision(
        eligible=eligible,
        reasons=tuple(reasons),
        probabilistic_eligible=probabilistic.eligible,
        conformal_eligible=conformal.eligible,
        probabilistic_folds=probabilistic.folds,
        conformal_scored_steps=conformal.scored_steps,
        uncertainty_step_ratio=ratio,
        probabilistic_decision_fingerprint=probabilistic.fingerprint,
        conformal_decision_fingerprint=conformal.fingerprint,
        gate_fingerprint=gate_fingerprint,
        fingerprint=fingerprint,
    )


def validate_joint_probabilistic_governance_decision(
    decision: JointProbabilisticGovernanceDecision,
) -> None:
    """Reject malformed or tampered joint governance evidence."""

    if not isinstance(decision, JointProbabilisticGovernanceDecision):
        raise StateSpaceError(
            "decision must be a JointProbabilisticGovernanceDecision",
            context={"reason": "invalid_joint_governance_decision"},
        )
    if not isinstance(decision.eligible, bool):
        raise StateSpaceError(
            "eligible must be a boolean",
            context={"reason": "invalid_joint_governance_decision"},
        )
    if not isinstance(decision.probabilistic_eligible, bool) or not isinstance(
        decision.conformal_eligible,
        bool,
    ):
        raise StateSpaceError(
            "child eligibility flags must be booleans",
            context={"reason": "invalid_joint_governance_decision"},
        )
    _positive_integer("probabilistic_folds", decision.probabilistic_folds)
    _positive_integer("conformal_scored_steps", decision.conformal_scored_steps)
    ratio = _positive("uncertainty_step_ratio", decision.uncertainty_step_ratio)
    expected_ratio = decision.conformal_scored_steps / decision.probabilistic_folds
    if abs(ratio - expected_ratio) > 1e-12:
        raise StateSpaceError(
            "uncertainty step ratio disagrees with evidence counts",
            context={"reason": "invalid_joint_governance_decision"},
        )
    _validate_reasons(decision.reasons, eligible=decision.eligible)
    for name, value in (
        (
            "probabilistic_decision_fingerprint",
            decision.probabilistic_decision_fingerprint,
        ),
        ("conformal_decision_fingerprint", decision.conformal_decision_fingerprint),
        ("gate_fingerprint", decision.gate_fingerprint),
        ("fingerprint", decision.fingerprint),
    ):
        _validate_digest(name, value)

    expected = _decision_fingerprint(
        eligible=decision.eligible,
        reasons=decision.reasons,
        probabilistic_eligible=decision.probabilistic_eligible,
        conformal_eligible=decision.conformal_eligible,
        probabilistic_folds=decision.probabilistic_folds,
        conformal_scored_steps=decision.conformal_scored_steps,
        uncertainty_step_ratio=decision.uncertainty_step_ratio,
        probabilistic_decision_fingerprint=decision.probabilistic_decision_fingerprint,
        conformal_decision_fingerprint=decision.conformal_decision_fingerprint,
        gate_fingerprint=decision.gate_fingerprint,
    )
    if decision.fingerprint != expected:
        raise StateSpaceError(
            "joint probabilistic governance decision fingerprint mismatch",
            context={"reason": "joint_governance_identity_mismatch"},
        )


def _gate_fingerprint(gate: JointProbabilisticGovernanceGate) -> str:
    return _digest(
        {
            "schema": "jeeves.joint-probabilistic-governance-gate.v1",
            "require_probabilistic_eligible": gate.require_probabilistic_eligible,
            "require_conformal_eligible": gate.require_conformal_eligible,
            "min_uncertainty_step_ratio": gate.min_uncertainty_step_ratio,
            "max_uncertainty_step_ratio": gate.max_uncertainty_step_ratio,
        }
    )


def _decision_fingerprint(
    *,
    eligible: bool,
    reasons: tuple[str, ...],
    probabilistic_eligible: bool,
    conformal_eligible: bool,
    probabilistic_folds: int,
    conformal_scored_steps: int,
    uncertainty_step_ratio: float,
    probabilistic_decision_fingerprint: str,
    conformal_decision_fingerprint: str,
    gate_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.joint-probabilistic-governance-decision.v1",
            "eligible": eligible,
            "reasons": list(reasons),
            "probabilistic_eligible": probabilistic_eligible,
            "conformal_eligible": conformal_eligible,
            "probabilistic_folds": probabilistic_folds,
            "conformal_scored_steps": conformal_scored_steps,
            "uncertainty_step_ratio": uncertainty_step_ratio,
            "probabilistic_decision_fingerprint": probabilistic_decision_fingerprint,
            "conformal_decision_fingerprint": conformal_decision_fingerprint,
            "gate_fingerprint": gate_fingerprint,
        }
    )


def _validate_reasons(reasons: tuple[str, ...], *, eligible: bool) -> None:
    if not isinstance(reasons, tuple) or not reasons:
        raise StateSpaceError(
            "reasons must be a non-empty tuple",
            context={"reason": "invalid_joint_governance_decision"},
        )
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        raise StateSpaceError(
            "reasons must contain non-empty strings",
            context={"reason": "invalid_joint_governance_decision"},
        )
    passed = "joint_probabilistic_evidence_gate_passed" in reasons
    if eligible != passed or (passed and len(reasons) != 1):
        raise StateSpaceError(
            "joint reasons disagree with eligibility",
            context={"reason": "invalid_joint_governance_decision"},
        )


def _validate_digest(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_joint_governance_decision"},
        )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_joint_governance_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_joint_governance_gate", "field": name},
        )
    return number


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_joint_governance_gate", "field": name},
        )
    return number


def _positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateSpaceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_joint_governance_decision", "field": name},
        )
    return value


__all__ = [
    "JointProbabilisticGovernanceDecision",
    "JointProbabilisticGovernanceGate",
    "evaluate_joint_probabilistic_governance",
    "validate_joint_probabilistic_governance_decision",
]
