"""Evidence-derived Definition of Done contracts for VOL-110.

This module evaluates whether an exact immutable subject has enough evidence to
claim a target maturity. It never mutates masterplan/accountability state and it
never signs completion on behalf of a reviewer.

The policy is impact-aware: rollback, recovery, migration, observability and
security evidence become mandatory only when the declared change impacts make
them applicable. Completion is fail-closed and binds an independent signoff to
the exact policy, target maturity and evidence set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

from .maturity_reconciliation import MATURITY_ORDER, MaturityState
from .promotion_evidence import PromotionEvidenceReceipt

DOD_SCHEMA = "skeleton.contracts.definition_of_done.v1"
_MAX_REQUIREMENTS = 256
_MAX_EVIDENCE = 4096
_MAX_AGE_SECONDS = 31_536_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_MATURITY_INDEX = {state: index for index, state in enumerate(MATURITY_ORDER)}


class DefinitionOfDoneError(ValueError):
    """Definition-of-Done state is malformed or unsafe to evaluate."""


class ChangeImpact(str, Enum):
    LOGIC = "logic"
    USER_VISIBLE = "user_visible"
    SECURITY = "security"
    AUTHORITY = "authority"
    PERSISTENCE = "persistence"
    SCHEMA = "schema"
    DATA_MIGRATION = "data_migration"
    EXTERNAL_EFFECT = "external_effect"
    DEPENDENCY = "dependency"
    RELEASE = "release"


class EvidenceKind(str, Enum):
    IMPLEMENTATION = "implementation"
    TEST = "test"
    FAILURE_BEHAVIOR = "failure_behavior"
    RECOVERY = "recovery"
    OBSERVABILITY = "observability"
    ROLLBACK = "rollback"
    OWNERSHIP = "ownership"
    SECURITY_REVIEW = "security_review"
    MIGRATION = "migration"
    INDEPENDENT_VERIFICATION = "independent_verification"
    RISK_REVIEW = "risk_review"
    PROMOTION = "promotion"


class RequirementStatus(str, Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    FAILED = "failed"
    STALE = "stale"
    INDEPENDENCE_VIOLATION = "independence_violation"
    OWNER_MISMATCH = "owner_mismatch"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise DefinitionOfDoneError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise DefinitionOfDoneError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise DefinitionOfDoneError(f"{field} contains control characters")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DefinitionOfDoneError(f"{field} must be lowercase sha256")
    return value


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DefinitionOfDoneError(f"{field} must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        raise DefinitionOfDoneError(f"{field} must use whole-second precision")
    return normalized


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DefinitionOfDoneError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise DefinitionOfDoneError(f"{field} must be within [1, {maximum}]")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DefinitionOfDoneError("value must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ChangeImpactProfile:
    subject_id: str
    subject_digest: str
    owner_id: str
    builder_id: str
    impacts: tuple[ChangeImpact, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _token(self.subject_id, "subject_id"))
        object.__setattr__(
            self,
            "subject_digest",
            _sha(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(self, "owner_id", _token(self.owner_id, "owner_id"))
        object.__setattr__(self, "builder_id", _token(self.builder_id, "builder_id"))
        if not isinstance(self.impacts, tuple) or not self.impacts:
            raise DefinitionOfDoneError("impacts must be a non-empty tuple")
        normalized: list[ChangeImpact] = []
        for item in self.impacts:
            if not isinstance(item, ChangeImpact):
                raise DefinitionOfDoneError("impacts must contain ChangeImpact")
            if item in normalized:
                raise DefinitionOfDoneError("duplicate change impact")
            normalized.append(item)
        object.__setattr__(
            self,
            "impacts",
            tuple(sorted(normalized, key=lambda item: item.value)),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.subject_id,
                self.subject_digest,
                self.owner_id,
                self.builder_id,
                [item.value for item in self.impacts],
            ]
        )


@dataclass(frozen=True, slots=True)
class DoDRequirement:
    requirement_id: str
    evidence_kind: EvidenceKind
    statement: str
    minimum_maturity: MaturityState
    triggers: tuple[ChangeImpact, ...] = ()
    always_required: bool = False
    independent: bool = False
    max_age_seconds: int = _MAX_AGE_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _token(self.requirement_id, "requirement_id"),
        )
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise DefinitionOfDoneError("evidence_kind must be EvidenceKind")
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        if not isinstance(self.minimum_maturity, MaturityState):
            raise DefinitionOfDoneError("minimum_maturity must be MaturityState")
        if not isinstance(self.triggers, tuple):
            raise DefinitionOfDoneError("triggers must be a tuple")
        normalized: list[ChangeImpact] = []
        for trigger in self.triggers:
            if not isinstance(trigger, ChangeImpact):
                raise DefinitionOfDoneError("triggers must contain ChangeImpact")
            if trigger in normalized:
                raise DefinitionOfDoneError("duplicate impact trigger")
            normalized.append(trigger)
        object.__setattr__(
            self,
            "triggers",
            tuple(sorted(normalized, key=lambda item: item.value)),
        )
        if not isinstance(self.always_required, bool):
            raise DefinitionOfDoneError("always_required must be boolean")
        if not isinstance(self.independent, bool):
            raise DefinitionOfDoneError("independent must be boolean")
        if not self.always_required and not self.triggers:
            raise DefinitionOfDoneError(
                "requirement must be always-required or impact-triggered"
            )
        object.__setattr__(
            self,
            "max_age_seconds",
            _positive_int(
                self.max_age_seconds,
                "max_age_seconds",
                _MAX_AGE_SECONDS,
            ),
        )

    def applies(
        self,
        *,
        impacts: tuple[ChangeImpact, ...],
        target_maturity: MaturityState,
    ) -> bool:
        if _MATURITY_INDEX[target_maturity] < _MATURITY_INDEX[self.minimum_maturity]:
            return False
        return self.always_required or any(item in impacts for item in self.triggers)

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.requirement_id,
                self.evidence_kind.value,
                self.statement,
                self.minimum_maturity.value,
                [item.value for item in self.triggers],
                self.always_required,
                self.independent,
                self.max_age_seconds,
            ]
        )


@dataclass(frozen=True, slots=True)
class DefinitionOfDone:
    policy_id: str
    version: int
    requirements: tuple[DoDRequirement, ...]
    independent_signoff_required: bool = True
    signoff_max_age_seconds: int = 2_592_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version", 1_000_000_000),
        )
        if (
            not isinstance(self.requirements, tuple)
            or not self.requirements
            or len(self.requirements) > _MAX_REQUIREMENTS
        ):
            raise DefinitionOfDoneError("requirements are outside policy bounds")
        normalized = tuple(
            sorted(self.requirements, key=lambda item: item.requirement_id)
        )
        ids = [item.requirement_id for item in normalized]
        if len(ids) != len(set(ids)):
            raise DefinitionOfDoneError("duplicate DoD requirement id")
        object.__setattr__(self, "requirements", normalized)
        if self.independent_signoff_required is not True:
            raise DefinitionOfDoneError(
                "independent signoff is mandatory for Definition of Done"
            )
        object.__setattr__(
            self,
            "signoff_max_age_seconds",
            _positive_int(
                self.signoff_max_age_seconds,
                "signoff_max_age_seconds",
                _MAX_AGE_SECONDS,
            ),
        )

    def active_requirements(
        self,
        *,
        profile: ChangeImpactProfile,
        target_maturity: MaturityState,
    ) -> tuple[DoDRequirement, ...]:
        if not isinstance(profile, ChangeImpactProfile):
            raise TypeError("profile must be ChangeImpactProfile")
        if not isinstance(target_maturity, MaturityState):
            raise TypeError("target_maturity must be MaturityState")
        if _MATURITY_INDEX[target_maturity] < _MATURITY_INDEX[MaturityState.IMPLEMENTED]:
            raise DefinitionOfDoneError(
                "Definition of Done applies at implemented maturity or above"
            )
        active = tuple(
            item
            for item in self.requirements
            if item.applies(
                impacts=profile.impacts,
                target_maturity=target_maturity,
            )
        )
        if not active:
            raise DefinitionOfDoneError("policy produced no active requirements")
        return active

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.policy_id,
                self.version,
                [item.digest for item in self.requirements],
                self.independent_signoff_required,
                self.signoff_max_age_seconds,
            ]
        )


@dataclass(frozen=True, slots=True)
class CompletionEvidence:
    evidence_id: str
    requirement_id: str
    evidence_kind: EvidenceKind
    subject_digest: str
    artifact_digest: str
    producer_id: str
    verifier_id: str
    observed_at: datetime
    passed: bool

    def __post_init__(self) -> None:
        for field in (
            "evidence_id",
            "requirement_id",
            "producer_id",
            "verifier_id",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise DefinitionOfDoneError("evidence_kind must be EvidenceKind")
        object.__setattr__(
            self,
            "subject_digest",
            _sha(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        if not isinstance(self.passed, bool):
            raise DefinitionOfDoneError("passed must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.evidence_id,
                self.requirement_id,
                self.evidence_kind.value,
                self.subject_digest,
                self.artifact_digest,
                self.producer_id,
                self.verifier_id,
                self.observed_at.isoformat(),
                self.passed,
            ]
        )


@dataclass(frozen=True, slots=True)
class CompletionSignoff:
    signoff_id: str
    subject_digest: str
    policy_digest: str
    target_maturity: MaturityState
    evidence_set_digest: str
    signer_id: str
    observed_at: datetime
    approved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "signoff_id", _token(self.signoff_id, "signoff_id"))
        object.__setattr__(
            self,
            "subject_digest",
            _sha(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _sha(self.policy_digest, "policy_digest"),
        )
        if not isinstance(self.target_maturity, MaturityState):
            raise DefinitionOfDoneError("target_maturity must be MaturityState")
        object.__setattr__(
            self,
            "evidence_set_digest",
            _sha(self.evidence_set_digest, "evidence_set_digest"),
        )
        object.__setattr__(self, "signer_id", _token(self.signer_id, "signer_id"))
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        if not isinstance(self.approved, bool):
            raise DefinitionOfDoneError("approved must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.signoff_id,
                self.subject_digest,
                self.policy_digest,
                self.target_maturity.value,
                self.evidence_set_digest,
                self.signer_id,
                self.observed_at.isoformat(),
                self.approved,
            ]
        )


@dataclass(frozen=True, slots=True)
class DoDRequirementEvaluation:
    requirement_id: str
    status: RequirementStatus
    evidence_digest: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class CompletionEvaluation:
    subject_id: str
    subject_digest: str
    profile_digest: str
    policy_digest: str
    target_maturity: MaturityState
    assessed_at: datetime
    requirements: tuple[DoDRequirementEvaluation, ...]
    evidence_set_digest: str
    signoff_digest: str | None
    eligible: bool
    blockers: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(
            [
                DOD_SCHEMA,
                self.subject_id,
                self.subject_digest,
                self.profile_digest,
                self.policy_digest,
                self.target_maturity.value,
                self.assessed_at.isoformat(),
                [
                    (
                        item.requirement_id,
                        item.status.value,
                        item.evidence_digest,
                        item.reason,
                    )
                    for item in self.requirements
                ],
                self.evidence_set_digest,
                self.signoff_digest,
                self.eligible,
                self.blockers,
            ]
        )


class DefinitionOfDoneEvaluator:
    """Derive exact completion eligibility from policy, impacts and evidence."""

    def evaluate(
        self,
        *,
        policy: DefinitionOfDone,
        profile: ChangeImpactProfile,
        target_maturity: MaturityState,
        evidence: Iterable[CompletionEvidence],
        signoff: CompletionSignoff | None,
        at: datetime,
    ) -> CompletionEvaluation:
        if not isinstance(policy, DefinitionOfDone):
            raise TypeError("policy must be DefinitionOfDone")
        if not isinstance(profile, ChangeImpactProfile):
            raise TypeError("profile must be ChangeImpactProfile")
        if not isinstance(target_maturity, MaturityState):
            raise TypeError("target_maturity must be MaturityState")
        now = _utc(at, "assessment time")
        active = policy.active_requirements(
            profile=profile,
            target_maturity=target_maturity,
        )
        requirement_by_id = {
            item.requirement_id: item for item in policy.requirements
        }

        materialized = tuple(evidence)
        if len(materialized) > _MAX_EVIDENCE:
            raise DefinitionOfDoneError("evidence set exceeds policy bound")
        evidence_ids: set[str] = set()
        by_requirement: dict[str, list[CompletionEvidence]] = {}
        for item in materialized:
            if not isinstance(item, CompletionEvidence):
                raise TypeError("evidence must contain CompletionEvidence")
            if item.evidence_id in evidence_ids:
                raise DefinitionOfDoneError("duplicate completion evidence id")
            evidence_ids.add(item.evidence_id)
            if item.requirement_id not in requirement_by_id:
                raise DefinitionOfDoneError(
                    "evidence references unknown DoD requirement"
                )
            by_requirement.setdefault(item.requirement_id, []).append(item)

        evaluations: list[DoDRequirementEvaluation] = []
        accepted_digests: list[str] = []
        accepted_evidence: list[CompletionEvidence] = []

        for requirement in active:
            candidates = [
                item
                for item in by_requirement.get(requirement.requirement_id, ())
                if item.subject_digest == profile.subject_digest
                and item.evidence_kind is requirement.evidence_kind
                and item.observed_at <= now
            ]
            if not candidates:
                evaluations.append(
                    DoDRequirementEvaluation(
                        requirement.requirement_id,
                        RequirementStatus.MISSING,
                        None,
                        "no exact subject/kind evidence",
                    )
                )
                continue

            latest = max(
                candidates,
                key=lambda item: (item.observed_at, item.digest),
            )
            age = (now - latest.observed_at).total_seconds()
            if age > requirement.max_age_seconds:
                status = RequirementStatus.STALE
                reason = "latest exact evidence exceeded freshness policy"
            elif not latest.passed:
                status = RequirementStatus.FAILED
                reason = "latest exact evidence reports failure"
            elif (
                requirement.evidence_kind is EvidenceKind.OWNERSHIP
                and latest.producer_id != profile.owner_id
            ):
                status = RequirementStatus.OWNER_MISMATCH
                reason = "ownership evidence was not produced by declared owner"
            elif (
                requirement.independent
                and (
                    latest.verifier_id == latest.producer_id
                    or latest.verifier_id == profile.builder_id
                    or latest.verifier_id == profile.owner_id
                )
            ):
                status = RequirementStatus.INDEPENDENCE_VIOLATION
                reason = "requirement needs a verifier independent of producer/builder"
            else:
                status = RequirementStatus.SATISFIED
                reason = "fresh exact evidence satisfies requirement"
                accepted_digests.append(latest.digest)
                accepted_evidence.append(latest)

            evaluations.append(
                DoDRequirementEvaluation(
                    requirement.requirement_id,
                    status,
                    latest.digest,
                    reason,
                )
            )

        evidence_set_digest = _digest(sorted(accepted_digests))
        blockers = [
            f"{item.requirement_id}:{item.status.value}"
            for item in evaluations
            if item.status is not RequirementStatus.SATISFIED
        ]

        signoff_digest: str | None = None
        if policy.independent_signoff_required:
            if signoff is None:
                blockers.append("independent_signoff:missing")
            else:
                signoff_digest = signoff.digest
                if signoff.subject_digest != profile.subject_digest:
                    blockers.append("independent_signoff:subject_mismatch")
                if signoff.policy_digest != policy.digest:
                    blockers.append("independent_signoff:policy_mismatch")
                if signoff.target_maturity is not target_maturity:
                    blockers.append("independent_signoff:maturity_mismatch")
                if signoff.evidence_set_digest != evidence_set_digest:
                    blockers.append("independent_signoff:evidence_set_mismatch")
                if signoff.observed_at > now:
                    blockers.append("independent_signoff:future")
                elif (
                    now - signoff.observed_at
                ).total_seconds() > policy.signoff_max_age_seconds:
                    blockers.append("independent_signoff:stale")
                if accepted_evidence and signoff.observed_at < max(
                    item.observed_at for item in accepted_evidence
                ):
                    blockers.append("independent_signoff:predates_evidence")
                if not signoff.approved:
                    blockers.append("independent_signoff:rejected")
                if signoff.signer_id in {
                    profile.builder_id,
                    profile.owner_id,
                }:
                    blockers.append("independent_signoff:not_independent")

        blockers = sorted(set(blockers))
        return CompletionEvaluation(
            subject_id=profile.subject_id,
            subject_digest=profile.subject_digest,
            profile_digest=profile.digest,
            policy_digest=policy.digest,
            target_maturity=target_maturity,
            assessed_at=now,
            requirements=tuple(evaluations),
            evidence_set_digest=evidence_set_digest,
            signoff_digest=signoff_digest,
            eligible=not blockers,
            blockers=tuple(blockers),
        )


def completion_evidence_from_promotion_receipt(
    *,
    evidence_id: str,
    requirement_id: str,
    producer_id: str,
    receipt: PromotionEvidenceReceipt,
    passed: bool = True,
) -> CompletionEvidence:
    """Bind production DoD evidence to an exact promotion receipt."""

    if not isinstance(receipt, PromotionEvidenceReceipt):
        raise TypeError("receipt must be PromotionEvidenceReceipt")
    return CompletionEvidence(
        evidence_id=evidence_id,
        requirement_id=requirement_id,
        evidence_kind=EvidenceKind.PROMOTION,
        subject_digest=receipt.subject_digest,
        artifact_digest=receipt.receipt_digest,
        producer_id=producer_id,
        verifier_id=receipt.verifier_id,
        observed_at=receipt.observed_at,
        passed=passed,
    )


def default_definition_of_done() -> DefinitionOfDone:
    """Repository default DoD policy for implemented-and-above maturity."""

    high_risk = (
        ChangeImpact.SECURITY,
        ChangeImpact.AUTHORITY,
        ChangeImpact.PERSISTENCE,
        ChangeImpact.EXTERNAL_EFFECT,
    )
    rollback_impacts = (
        ChangeImpact.PERSISTENCE,
        ChangeImpact.SCHEMA,
        ChangeImpact.DATA_MIGRATION,
        ChangeImpact.DEPENDENCY,
        ChangeImpact.EXTERNAL_EFFECT,
        ChangeImpact.RELEASE,
    )
    recovery_impacts = (
        ChangeImpact.PERSISTENCE,
        ChangeImpact.DATA_MIGRATION,
        ChangeImpact.EXTERNAL_EFFECT,
        ChangeImpact.RELEASE,
    )
    observable_impacts = (
        ChangeImpact.USER_VISIBLE,
        ChangeImpact.SECURITY,
        ChangeImpact.AUTHORITY,
        ChangeImpact.PERSISTENCE,
        ChangeImpact.EXTERNAL_EFFECT,
        ChangeImpact.RELEASE,
    )

    return DefinitionOfDone(
        policy_id="repository.dod.v1",
        version=1,
        requirements=(
            DoDRequirement(
                "dod.implementation",
                EvidenceKind.IMPLEMENTATION,
                "Canonical implementation exists for the exact subject.",
                MaturityState.IMPLEMENTED,
                always_required=True,
            ),
            DoDRequirement(
                "dod.tests",
                EvidenceKind.TEST,
                "Focused regression evidence passes for the exact subject.",
                MaturityState.IMPLEMENTED,
                always_required=True,
            ),
            DoDRequirement(
                "dod.ownership",
                EvidenceKind.OWNERSHIP,
                "A named canonical owner accepts custody for the exact subject.",
                MaturityState.IMPLEMENTED,
                always_required=True,
            ),
            DoDRequirement(
                "dod.failure_behavior",
                EvidenceKind.FAILURE_BEHAVIOR,
                "Applicable failure and stop behavior is exercised.",
                MaturityState.IMPLEMENTED,
                triggers=(
                    ChangeImpact.LOGIC,
                    *high_risk,
                    ChangeImpact.DEPENDENCY,
                ),
            ),
            DoDRequirement(
                "dod.observability",
                EvidenceKind.OBSERVABILITY,
                "Applicable operation/failure behavior is observable.",
                MaturityState.INTEGRATED,
                triggers=observable_impacts,
            ),
            DoDRequirement(
                "dod.rollback",
                EvidenceKind.ROLLBACK,
                "A reversible rollback path is evidenced for applicable change impact.",
                MaturityState.INTEGRATED,
                triggers=rollback_impacts,
            ),
            DoDRequirement(
                "dod.recovery",
                EvidenceKind.RECOVERY,
                "Recovery/restart behavior is evidenced where state or effects can diverge.",
                MaturityState.INTEGRATED,
                triggers=recovery_impacts,
            ),
            DoDRequirement(
                "dod.migration",
                EvidenceKind.MIGRATION,
                "Schema/data migration behavior is evidenced.",
                MaturityState.INTEGRATED,
                triggers=(
                    ChangeImpact.SCHEMA,
                    ChangeImpact.DATA_MIGRATION,
                ),
            ),
            DoDRequirement(
                "dod.security_review",
                EvidenceKind.SECURITY_REVIEW,
                "Security/authority impact receives independent review.",
                MaturityState.VERIFIED,
                triggers=(
                    ChangeImpact.SECURITY,
                    ChangeImpact.AUTHORITY,
                ),
                independent=True,
            ),
            DoDRequirement(
                "dod.independent_verification",
                EvidenceKind.INDEPENDENT_VERIFICATION,
                "Independent verification covers the exact subject.",
                MaturityState.VERIFIED,
                always_required=True,
                independent=True,
            ),
            DoDRequirement(
                "dod.risk_review",
                EvidenceKind.RISK_REVIEW,
                "High-impact change has explicit risk disposition evidence.",
                MaturityState.HARDENED,
                triggers=high_risk + (ChangeImpact.RELEASE,),
                independent=True,
            ),
            DoDRequirement(
                "dod.promotion",
                EvidenceKind.PROMOTION,
                "Production maturity binds an exact independent promotion receipt.",
                MaturityState.PRODUCTION,
                always_required=True,
                independent=True,
            ),
        ),
    )


__all__ = [
    "DOD_SCHEMA",
    "ChangeImpact",
    "ChangeImpactProfile",
    "CompletionEvidence",
    "CompletionEvaluation",
    "CompletionSignoff",
    "DefinitionOfDone",
    "DefinitionOfDoneError",
    "DefinitionOfDoneEvaluator",
    "DoDRequirement",
    "DoDRequirementEvaluation",
    "EvidenceKind",
    "RequirementStatus",
    "completion_evidence_from_promotion_receipt",
    "default_definition_of_done",
]
