"""Deterministic human-factors assessment for VOL-326.

This plane observes operator burden and presentation risk.  It never grants
authority, reuses approvals, executes actions, or overrides an existing
security/governance decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable


class HumanFactorsError(ValueError):
    """Human-factors evidence is malformed or internally inconsistent."""


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class InteractionObservation:
    task_id: str
    approvals_requested: int
    approvals_overridden: int
    interruptions: int
    elapsed_seconds: int
    confidence: float
    uncertainty: float
    degraded: bool
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise HumanFactorsError("task_id must be non-empty canonical text")
        counts = (self.approvals_requested, self.approvals_overridden, self.interruptions, self.elapsed_seconds)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts):
            raise HumanFactorsError("interaction counts must be non-negative integers")
        if self.approvals_overridden > self.approvals_requested:
            raise HumanFactorsError("overrides cannot exceed requested approvals")
        for value in (self.confidence, self.uncertainty):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise HumanFactorsError("confidence and uncertainty must be finite probabilities")
        if not isinstance(self.degraded, bool):
            raise HumanFactorsError("degraded must be boolean")
        if not self.evidence or len(self.evidence) != len(set(self.evidence)):
            raise HumanFactorsError("unique evidence is required")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence):
            raise HumanFactorsError("evidence references must be non-empty text")

    def digest(self) -> str:
        return _canonical_digest({
            "approvals_overridden": self.approvals_overridden,
            "approvals_requested": self.approvals_requested,
            "confidence": self.confidence,
            "degraded": self.degraded,
            "elapsed_seconds": self.elapsed_seconds,
            "evidence": list(self.evidence),
            "interruptions": self.interruptions,
            "task_id": self.task_id,
            "uncertainty": self.uncertainty,
        })


@dataclass(frozen=True, slots=True)
class HumanFactorsPolicy:
    max_approvals: int = 5
    max_interruptions: int = 3
    max_elapsed_seconds: int = 3600
    max_uncertainty: float = 0.5

    def __post_init__(self) -> None:
        for value in (self.max_approvals, self.max_interruptions, self.max_elapsed_seconds):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise HumanFactorsError("policy integer bounds must be positive")
        if isinstance(self.max_uncertainty, bool) or not isinstance(self.max_uncertainty, (int, float)) or not math.isfinite(self.max_uncertainty) or not 0 <= self.max_uncertainty <= 1:
            raise HumanFactorsError("max_uncertainty must be a finite probability")


@dataclass(frozen=True, slots=True)
class HumanFactorsAssessment:
    task_id: str
    risk: str
    reasons: tuple[str, ...]
    mitigations: tuple[str, ...]
    observation_digest: str
    decision_digest: str
    authority_scope: str = "evidence-only"

    @property
    def requires_human_review(self) -> bool:
        return self.risk == "high"


def assess_human_factors(observation: InteractionObservation, policy: HumanFactorsPolicy = HumanFactorsPolicy()) -> HumanFactorsAssessment:
    if not isinstance(observation, InteractionObservation) or not isinstance(policy, HumanFactorsPolicy):
        raise HumanFactorsError("typed observation and policy are required")
    reasons: list[str] = []
    mitigations: list[str] = []
    if observation.approvals_requested > policy.max_approvals:
        reasons.append("approval-burden")
        mitigations.append("reduce-or-batch-non-authority-prompts")
    if observation.approvals_overridden:
        reasons.append("approval-overrides")
        mitigations.append("require-fresh-explicit-approval")
    if observation.interruptions > policy.max_interruptions:
        reasons.append("interruption-load")
        mitigations.append("surface-resumable-checkpoint")
    if observation.elapsed_seconds > policy.max_elapsed_seconds:
        reasons.append("long-running-task")
        mitigations.append("surface-progress-and-current-authority")
    if observation.uncertainty > policy.max_uncertainty or observation.degraded:
        reasons.append("trust-calibration-risk")
        mitigations.append("surface-uncertainty-and-degraded-state")
    # Low confidence never silently cancels uncertainty/degraded evidence.
    if observation.confidence < 0.5:
        reasons.append("low-confidence")
        mitigations.append("request-independent-evidence")
    reasons_t = tuple(sorted(set(reasons)))
    mitigations_t = tuple(sorted(set(mitigations)))
    risk = "high" if observation.degraded or observation.approvals_overridden or len(reasons_t) >= 3 else ("medium" if reasons_t else "low")
    obs_digest = observation.digest()
    decision_digest = _canonical_digest({
        "authority_scope": "evidence-only",
        "mitigations": list(mitigations_t),
        "observation_digest": obs_digest,
        "reasons": list(reasons_t),
        "risk": risk,
        "task_id": observation.task_id,
    })
    return HumanFactorsAssessment(observation.task_id, risk, reasons_t, mitigations_t, obs_digest, decision_digest)


def aggregate_assessments(assessments: Iterable[HumanFactorsAssessment]) -> tuple[HumanFactorsAssessment, ...]:
    items = tuple(assessments)
    if len({item.task_id for item in items}) != len(items):
        raise HumanFactorsError("duplicate task assessments are ambiguous")
    if any(item.authority_scope != "evidence-only" for item in items):
        raise HumanFactorsError("human-factors assessments cannot carry execution authority")
    return tuple(sorted(items, key=lambda item: item.task_id))
