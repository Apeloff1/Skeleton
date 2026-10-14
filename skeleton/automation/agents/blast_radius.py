"""P1 blast-radius, reversibility, and adversarial-alignment qualification.

This module does not execute actions and does not grant authority. It classifies
one exact proposed action, binds the classification to delegated authority,
requires fresh independent adversarial review, and for high/critical actions
requires both an exact human approval receipt and a resolved EVID-04 risk
binding. Goal drift, specification gaming, policy conflict, deceptive behavior,
stale evidence, or approval drift fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Any, Iterable

from skeleton.automation.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.contracts.canonical import (
    CanonicalContractError,
    EvidenceRef,
    canonical_json_bytes,
    evidence_ref_identity,
)
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.contracts.safety_hazards import (
    DEFAULT_SAFETY_HAZARD_MANIFEST,
    DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST,
    DEFAULT_SAFETY_POLICY_ID,
    DEFAULT_SAFETY_POLICY_VERSION,
    SafetyHazardManifest,
)


BLAST_RADIUS_SCHEMA_VERSION = 1
BLAST_RADIUS_TASK_ID = "P1-AUTO-05"
BLAST_RADIUS_ACCOUNTABILITY_ID = "ACC-P1-AUTO-05"


class BlastRadiusError(ValueError):
    """Blast-radius or adversarial-alignment evidence is malformed."""


class ReversibilityClass(str, Enum):
    REVERSIBLE = "reversible"
    RECOVERABLE = "recoverable"
    IRREVERSIBLE = "irreversible"


class ImpactClass(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlastRadiusError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise BlastRadiusError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise BlastRadiusError(f"{field} must be lowercase sha256")
    return text


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BlastRadiusError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise BlastRadiusError(f"{field} must be finite numeric")
    return result


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BlastRadiusError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BlastRadiusError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        encoded = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise BlastRadiusError("blast-radius payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(values: Iterable[EvidenceRef], field: str) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise BlastRadiusError(f"{field} must contain EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise BlastRadiusError(f"{field} must contain EvidenceRef")
        _text(item.source, f"{field}.source")
        _sha256(item.digest, f"{field}.digest")
        _text(item.category, f"{field}.category", maximum=128)
        by_identity[evidence_ref_identity(item)] = item
    if not by_identity:
        raise BlastRadiusError(f"{field} requires materialized evidence")
    return tuple(by_identity[key] for key in sorted(by_identity))


def _refs_payload(values: tuple[EvidenceRef, ...]) -> list[dict[str, str]]:
    return [
        {
            "identity": evidence_ref_identity(item),
            "source": item.source,
            "digest": item.digest,
            "category": item.category,
        }
        for item in values
    ]


@dataclass(frozen=True, slots=True)
class BlastRadiusPolicy:
    max_tenants_without_human: int = 1
    max_resources_without_human: int = 25
    critical_tenant_threshold: int = 10
    critical_resource_threshold: int = 500
    require_independent_adversarial: bool = True
    hazard_manifest: SafetyHazardManifest = DEFAULT_SAFETY_HAZARD_MANIFEST

    def __post_init__(self) -> None:
        for field in (
            "max_tenants_without_human",
            "max_resources_without_human",
            "critical_tenant_threshold",
            "critical_resource_threshold",
        ):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )
        if self.critical_tenant_threshold <= self.max_tenants_without_human:
            raise BlastRadiusError(
                "critical_tenant_threshold must exceed human threshold"
            )
        if self.critical_resource_threshold <= self.max_resources_without_human:
            raise BlastRadiusError(
                "critical_resource_threshold must exceed human threshold"
            )
        if not isinstance(self.require_independent_adversarial, bool):
            raise BlastRadiusError(
                "require_independent_adversarial must be boolean"
            )
        if not isinstance(self.hazard_manifest, SafetyHazardManifest):
            raise BlastRadiusError(
                "hazard_manifest must be SafetyHazardManifest"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "max_tenants_without_human": self.max_tenants_without_human,
            "max_resources_without_human": self.max_resources_without_human,
            "critical_tenant_threshold": self.critical_tenant_threshold,
            "critical_resource_threshold": self.critical_resource_threshold,
            "require_independent_adversarial": self.require_independent_adversarial,
            "safety_policy_id": self.hazard_manifest.policy_id,
            "safety_policy_version": self.hazard_manifest.policy_version,
            "hazard_manifest_digest": self.hazard_manifest.manifest_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ActionRiskProfile:
    operation_id: str
    execution_id: str
    agent_id: str
    action_digest: str
    authority_digest: str
    affected_tenants: int
    affected_resources: int
    reversibility: ReversibilityClass
    writes_persistent_state: bool
    externally_observable: bool
    privileged: bool
    destructive: bool
    sensitive_data: bool
    recovery_plan_digest: str | None = None
    rollback_test_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in ("action_digest", "authority_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(
            self,
            "affected_tenants",
            _positive_int(self.affected_tenants, "affected_tenants"),
        )
        object.__setattr__(
            self,
            "affected_resources",
            _positive_int(self.affected_resources, "affected_resources"),
        )
        try:
            object.__setattr__(
                self,
                "reversibility",
                ReversibilityClass(self.reversibility),
            )
        except ValueError as exc:
            raise BlastRadiusError("invalid reversibility class") from exc
        for field in (
            "writes_persistent_state",
            "externally_observable",
            "privileged",
            "destructive",
            "sensitive_data",
        ):
            if not isinstance(getattr(self, field), bool):
                raise BlastRadiusError(f"{field} must be boolean")
        for field in ("recovery_plan_digest", "rollback_test_digest"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha256(value, field))
        if self.reversibility is ReversibilityClass.RECOVERABLE:
            if self.recovery_plan_digest is None:
                raise BlastRadiusError(
                    "recoverable action requires recovery_plan_digest"
                )
            if self.rollback_test_digest is None:
                raise BlastRadiusError(
                    "recoverable action requires rollback_test_digest"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "action_digest": self.action_digest,
            "authority_digest": self.authority_digest,
            "affected_tenants": self.affected_tenants,
            "affected_resources": self.affected_resources,
            "reversibility": self.reversibility.value,
            "writes_persistent_state": self.writes_persistent_state,
            "externally_observable": self.externally_observable,
            "privileged": self.privileged,
            "destructive": self.destructive,
            "sensitive_data": self.sensitive_data,
            "recovery_plan_digest": self.recovery_plan_digest,
            "rollback_test_digest": self.rollback_test_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AdversarialAlignmentReport:
    operation_id: str
    execution_id: str
    agent_id: str
    action_digest: str
    authority_digest: str
    verifier_id: str
    verifier_digest: str
    independent: bool
    goal_drift_detected: bool
    specification_gaming_detected: bool
    policy_conflict_detected: bool
    deceptive_behavior_detected: bool
    unresolved_counterexamples: int
    evidence_refs: tuple[EvidenceRef, ...]
    observed_at: float
    expires_at: float

    def __post_init__(self) -> None:
        for field in (
            "operation_id",
            "execution_id",
            "agent_id",
            "verifier_id",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in ("action_digest", "authority_digest", "verifier_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        for field in (
            "independent",
            "goal_drift_detected",
            "specification_gaming_detected",
            "policy_conflict_detected",
            "deceptive_behavior_detected",
        ):
            if not isinstance(getattr(self, field), bool):
                raise BlastRadiusError(f"{field} must be boolean")
        object.__setattr__(
            self,
            "unresolved_counterexamples",
            _non_negative_int(
                self.unresolved_counterexamples,
                "unresolved_counterexamples",
            ),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "adversarial evidence"),
        )
        observed = _finite(self.observed_at, "observed_at")
        expires = _finite(self.expires_at, "expires_at")
        if observed <= 0:
            raise BlastRadiusError("observed_at must be positive")
        if expires <= observed:
            raise BlastRadiusError("expires_at must be after observed_at")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "action_digest": self.action_digest,
            "authority_digest": self.authority_digest,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "independent": self.independent,
            "goal_drift_detected": self.goal_drift_detected,
            "specification_gaming_detected": self.specification_gaming_detected,
            "policy_conflict_detected": self.policy_conflict_detected,
            "deceptive_behavior_detected": self.deceptive_behavior_detected,
            "unresolved_counterexamples": self.unresolved_counterexamples,
            "evidence_refs": _refs_payload(self.evidence_refs),
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


def classify_impact(
    profile: ActionRiskProfile,
    *,
    policy: BlastRadiusPolicy | None = None,
) -> ImpactClass:
    if not isinstance(profile, ActionRiskProfile):
        raise TypeError("profile must be ActionRiskProfile")
    active = policy or BlastRadiusPolicy()
    if not isinstance(active, BlastRadiusPolicy):
        raise TypeError("policy must be BlastRadiusPolicy")

    if (
        profile.reversibility is ReversibilityClass.IRREVERSIBLE
        or profile.affected_tenants >= active.critical_tenant_threshold
        or profile.affected_resources >= active.critical_resource_threshold
        or (profile.destructive and profile.sensitive_data)
        or (profile.destructive and profile.privileged)
    ):
        return ImpactClass.CRITICAL

    if (
        profile.affected_tenants > active.max_tenants_without_human
        or profile.affected_resources > active.max_resources_without_human
        or profile.destructive
        or profile.privileged
        or profile.sensitive_data
        or (profile.externally_observable and profile.writes_persistent_state)
    ):
        return ImpactClass.HIGH

    if profile.writes_persistent_state or profile.externally_observable:
        return ImpactClass.MODERATE
    return ImpactClass.LOW


@dataclass(frozen=True, slots=True)
class BlastRadiusDecision:
    accepted: bool
    impact: ImpactClass
    reasons: tuple[str, ...]
    operation_id: str
    execution_id: str
    agent_id: str
    action_digest: str
    authority_digest: str
    profile_digest: str
    alignment_digest: str
    policy_digest: str
    risk_evaluation_digest: str | None
    human_receipt_digest: str | None
    safety_policy_id: str = DEFAULT_SAFETY_POLICY_ID
    safety_policy_version: int = DEFAULT_SAFETY_POLICY_VERSION
    hazard_manifest_digest: str = DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST
    triggered_hazard_ids: tuple[str, ...] = ()
    task_id: str = BLAST_RADIUS_TASK_ID
    accountability_id: str = BLAST_RADIUS_ACCOUNTABILITY_ID
    schema_version: int = BLAST_RADIUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BlastRadiusError("accepted must be boolean")
        try:
            object.__setattr__(self, "impact", ImpactClass(self.impact))
        except ValueError as exc:
            raise BlastRadiusError("invalid impact class") from exc
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise BlastRadiusError("reasons must contain non-empty strings")
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in (
            "action_digest",
            "authority_digest",
            "profile_digest",
            "alignment_digest",
            "policy_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        for field in ("risk_evaluation_digest", "human_receipt_digest"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha256(value, field))
        object.__setattr__(
            self,
            "safety_policy_id",
            _text(self.safety_policy_id, "safety_policy_id", maximum=256),
        )
        object.__setattr__(
            self,
            "safety_policy_version",
            _positive_int(self.safety_policy_version, "safety_policy_version"),
        )
        object.__setattr__(
            self,
            "hazard_manifest_digest",
            _sha256(self.hazard_manifest_digest, "hazard_manifest_digest"),
        )
        if not isinstance(self.triggered_hazard_ids, tuple):
            raise BlastRadiusError("triggered_hazard_ids must be a tuple")
        hazard_ids = tuple(
            _text(value, "triggered_hazard_ids", maximum=256)
            for value in self.triggered_hazard_ids
        )
        if hazard_ids != tuple(sorted(set(hazard_ids))):
            raise BlastRadiusError(
                "triggered_hazard_ids must be sorted unique canonical values"
            )
        object.__setattr__(self, "triggered_hazard_ids", hazard_ids)
        if self.task_id != BLAST_RADIUS_TASK_ID:
            raise BlastRadiusError("task_id drift")
        if self.accountability_id != BLAST_RADIUS_ACCOUNTABILITY_ID:
            raise BlastRadiusError("accountability_id drift")
        if self.schema_version != BLAST_RADIUS_SCHEMA_VERSION:
            raise BlastRadiusError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "impact": self.impact.value,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "action_digest": self.action_digest,
            "authority_digest": self.authority_digest,
            "profile_digest": self.profile_digest,
            "alignment_digest": self.alignment_digest,
            "policy_digest": self.policy_digest,
            "risk_evaluation_digest": self.risk_evaluation_digest,
            "human_receipt_digest": self.human_receipt_digest,
            "safety_policy_id": self.safety_policy_id,
            "safety_policy_version": self.safety_policy_version,
            "hazard_manifest_digest": self.hazard_manifest_digest,
            "triggered_hazard_ids": list(self.triggered_hazard_ids),
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-05:blast-radius-alignment",
    ) -> EvidenceRef:
        if not self.accepted:
            raise BlastRadiusError(
                "rejected blast-radius decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="blast_radius_alignment_qualification",
        )


def _risk_eval_digest(value: RiskBindingEvaluation | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, RiskBindingEvaluation):
        raise TypeError("risk_evaluation must be RiskBindingEvaluation")
    return _canonical_digest(value.as_dict())


def _hazard_signals(
    *,
    profile: ActionRiskProfile,
    alignment: AdversarialAlignmentReport,
    impact: ImpactClass,
    risk_evaluation: RiskBindingEvaluation | None,
    human_approval: HumanControlDecision | None,
) -> tuple[str, ...]:
    signals: set[str] = set()
    if profile.reversibility is ReversibilityClass.IRREVERSIBLE:
        signals.add("action.irreversible")
    if profile.destructive:
        signals.add("action.destructive")
    if profile.privileged:
        signals.add("action.privileged")
    if profile.sensitive_data:
        signals.add("data.sensitive")
    if profile.affected_tenants > 1:
        signals.add("scope.cross_tenant")
    if profile.externally_observable and profile.writes_persistent_state:
        signals.add("effect.external_persistent")
    if alignment.authority_digest != profile.authority_digest:
        signals.add("authority.mismatch")
    if alignment.goal_drift_detected:
        signals.add("alignment.goal_drift")
    if alignment.specification_gaming_detected:
        signals.add("alignment.specification_gaming")
    if alignment.policy_conflict_detected:
        signals.add("alignment.policy_conflict")
    if alignment.deceptive_behavior_detected:
        signals.add("alignment.deceptive_behavior")
    if alignment.unresolved_counterexamples:
        signals.add("alignment.counterexample")
    if (
        profile.reversibility is ReversibilityClass.RECOVERABLE
        and (
            profile.recovery_plan_digest is None
            or profile.rollback_test_digest is None
        )
    ):
        signals.add("recovery.evidence_missing")

    if impact in {ImpactClass.HIGH, ImpactClass.CRITICAL}:
        if risk_evaluation is None:
            signals.add("risk_binding.missing")
        elif (
            isinstance(risk_evaluation, RiskBindingEvaluation)
            and (not risk_evaluation.resolved or risk_evaluation.blockers)
        ):
            signals.add("risk_binding.unresolved")

        if human_approval is None:
            signals.add("approval.missing")
        elif isinstance(human_approval, HumanControlDecision):
            invalid_approval = (
                not human_approval.accepted
                or human_approval.action is not HumanControlAction.APPROVE
                or human_approval.operation_id != profile.operation_id
                or human_approval.execution_id != profile.execution_id
                or human_approval.agent_id != profile.agent_id
                or human_approval.arguments_digest != profile.action_digest
                or human_approval.authority_digest != profile.authority_digest
                or not human_approval.independent
            )
            if invalid_approval:
                signals.add("approval.invalid")
            if human_approval.authority_digest != profile.authority_digest:
                signals.add("authority.mismatch")

    return tuple(sorted(signals))


def qualify_blast_radius(
    *,
    profile: ActionRiskProfile,
    alignment: AdversarialAlignmentReport,
    observed_at: float,
    policy: BlastRadiusPolicy | None = None,
    risk_evaluation: RiskBindingEvaluation | None = None,
    human_approval: HumanControlDecision | None = None,
) -> BlastRadiusDecision:
    """Qualify an exact action without executing or authorizing the action."""

    if not isinstance(profile, ActionRiskProfile):
        raise TypeError("profile must be ActionRiskProfile")
    if not isinstance(alignment, AdversarialAlignmentReport):
        raise TypeError("alignment must be AdversarialAlignmentReport")
    active = policy or BlastRadiusPolicy()
    if not isinstance(active, BlastRadiusPolicy):
        raise TypeError("policy must be BlastRadiusPolicy")
    now = _finite(observed_at, "observed_at")
    if now <= 0:
        raise BlastRadiusError("observed_at must be positive")

    impact = classify_impact(profile, policy=active)
    reasons: list[str] = []

    if alignment.operation_id != profile.operation_id:
        reasons.append("alignment-operation-mismatch")
    if alignment.execution_id != profile.execution_id:
        reasons.append("alignment-execution-mismatch")
    if alignment.agent_id != profile.agent_id:
        reasons.append("alignment-agent-mismatch")
    if alignment.action_digest != profile.action_digest:
        reasons.append("alignment-action-mismatch")
    if alignment.authority_digest != profile.authority_digest:
        reasons.append("alignment-authority-mismatch")
    if alignment.verifier_id == profile.agent_id:
        reasons.append("alignment-verifier-is-agent")
    if active.require_independent_adversarial and not alignment.independent:
        reasons.append("alignment-not-independent")
    if now < alignment.observed_at:
        reasons.append("alignment-not-yet-valid")
    if now >= alignment.expires_at:
        reasons.append("alignment-expired")
    if alignment.goal_drift_detected:
        reasons.append("goal-drift-detected")
    if alignment.specification_gaming_detected:
        reasons.append("specification-gaming-detected")
    if alignment.policy_conflict_detected:
        reasons.append("policy-conflict-detected")
    if alignment.deceptive_behavior_detected:
        reasons.append("deceptive-behavior-detected")
    if alignment.unresolved_counterexamples:
        reasons.append("unresolved-counterexamples")

    if (
        profile.reversibility is ReversibilityClass.RECOVERABLE
        and (
            profile.recovery_plan_digest is None
            or profile.rollback_test_digest is None
        )
    ):
        reasons.append("recovery-evidence-missing")

    needs_high_controls = impact in {ImpactClass.HIGH, ImpactClass.CRITICAL}

    if needs_high_controls:
        if risk_evaluation is None:
            reasons.append("risk-binding-missing")
        else:
            if not isinstance(risk_evaluation, RiskBindingEvaluation):
                raise TypeError("risk_evaluation must be RiskBindingEvaluation")
            if not risk_evaluation.resolved or risk_evaluation.blockers:
                reasons.append("risk-binding-unresolved")
            if impact is ImpactClass.CRITICAL:
                if risk_evaluation.severity != "critical":
                    reasons.append("critical-risk-classification-mismatch")
            elif risk_evaluation.severity not in {"high", "critical"}:
                reasons.append("high-risk-classification-mismatch")

        if human_approval is None:
            reasons.append("human-approval-missing")
        else:
            if not isinstance(human_approval, HumanControlDecision):
                raise TypeError("human_approval must be HumanControlDecision")
            if not human_approval.accepted:
                reasons.append("human-approval-rejected")
            if human_approval.action is not HumanControlAction.APPROVE:
                reasons.append("human-approval-action-mismatch")
            if human_approval.operation_id != profile.operation_id:
                reasons.append("human-approval-operation-mismatch")
            if human_approval.execution_id != profile.execution_id:
                reasons.append("human-approval-execution-mismatch")
            if human_approval.agent_id != profile.agent_id:
                reasons.append("human-approval-agent-mismatch")
            if human_approval.arguments_digest != profile.action_digest:
                reasons.append("human-approval-action-digest-mismatch")
            if human_approval.authority_digest != profile.authority_digest:
                reasons.append("human-approval-authority-mismatch")
            if not human_approval.independent:
                reasons.append("human-approval-not-independent")
            if now >= human_approval.expires_at:
                reasons.append("human-approval-expired")

    normalized = tuple(sorted(set(reasons)))
    hazard_signals = _hazard_signals(
        profile=profile,
        alignment=alignment,
        impact=impact,
        risk_evaluation=risk_evaluation,
        human_approval=human_approval,
    )
    triggered_hazard_ids = active.hazard_manifest.hazards_for_signals(
        hazard_signals
    )
    return BlastRadiusDecision(
        accepted=not normalized,
        impact=impact,
        reasons=normalized,
        operation_id=profile.operation_id,
        execution_id=profile.execution_id,
        agent_id=profile.agent_id,
        action_digest=profile.action_digest,
        authority_digest=profile.authority_digest,
        profile_digest=profile.digest,
        alignment_digest=alignment.digest,
        policy_digest=active.digest,
        risk_evaluation_digest=_risk_eval_digest(risk_evaluation),
        human_receipt_digest=(
            None if human_approval is None else human_approval.receipt_digest
        ),
        safety_policy_id=active.hazard_manifest.policy_id,
        safety_policy_version=active.hazard_manifest.policy_version,
        hazard_manifest_digest=active.hazard_manifest.manifest_digest,
        triggered_hazard_ids=triggered_hazard_ids,
    )


__all__ = [
    "BLAST_RADIUS_ACCOUNTABILITY_ID",
    "BLAST_RADIUS_SCHEMA_VERSION",
    "BLAST_RADIUS_TASK_ID",
    "ActionRiskProfile",
    "AdversarialAlignmentReport",
    "BlastRadiusDecision",
    "BlastRadiusError",
    "BlastRadiusPolicy",
    "ImpactClass",
    "ReversibilityClass",
    "classify_impact",
    "qualify_blast_radius",
]
