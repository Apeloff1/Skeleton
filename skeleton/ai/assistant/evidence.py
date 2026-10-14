"""Deterministic evidence and citation publication gate for AI chat.

This module composes existing canonical verification contracts, citation
integrity, claim identity, and source metadata.  It does not retrieve sources,
call models, decide truth from confidence, or publish text.  Its sole authority
is to produce a deterministic evidence receipt describing whether a claim has
enough inspectable support to be eligible for downstream publication.

October 2026 invariants:

* citation proximity is never evidence; claim-level binding is mandatory;
* evidence content digest, source identity, locator, tenant, claim, and scope
  remain bound end-to-end;
* source quality is explicit metadata, never inferred from model prose;
* current/freshness requirements fail closed on stale or future evidence;
* model-produced evidence is never authoritative;
* correlated copies do not satisfy independent-origin requirements;
* authoritative contradiction produces a contested disposition;
* high/critical-risk claims can require primary-source support and additional
  independent origins;
* all receipts are deterministic, non-executing, and digest-bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Sequence

from skeleton.contracts.verification import (
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    VerificationClaim,
    VerificationRisk,
)
from skeleton.retrieval.verification import validate_citation as validate_reference
from skeleton.verification.citation_integrity import (
    CitationBinding,
    CitationIntegrityEngine,
)
from skeleton.verification.claim_identity import ClaimIdentityEngine


EVIDENCE_CITATION_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#@-]{0,191}$")


class EvidencePlaneError(ValueError):
    """Evidence publication inputs are malformed or authority is ambiguous."""


class PublicationDisposition(str, Enum):
    PUBLISH = "publish"
    PUBLISH_WITH_QUALIFICATION = "publish_with_qualification"
    CONTESTED = "contested"
    ABSTAIN = "abstain"


class SourceClass(str, Enum):
    PRIMARY = "primary"
    OFFICIAL = "official"
    SECONDARY = "secondary"
    COMMUNITY = "community"
    GENERATED = "generated"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidencePlaneError("value is not canonical-json encodable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise EvidencePlaneError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EvidencePlaneError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidencePlaneError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidencePlaneError(f"{field} must be finite numeric")
    if minimum is not None and result < minimum:
        raise EvidencePlaneError(f"{field} must be >= {minimum}")
    return result


def _unit(value: object, field: str) -> float:
    result = _finite(value, field, minimum=0.0)
    if result > 1.0:
        raise EvidencePlaneError(f"{field} must be <= 1.0")
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidencePlaneError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result < 1:
        raise EvidencePlaneError(f"{field} must be positive")
    return result


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise EvidencePlaneError(f"{field} must be timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class SourceQualityProfile:
    """Explicit source metadata supplied by a governed retrieval adapter."""

    source_id: str
    source_class: SourceClass | str
    quality_score: float
    provenance_verified: bool
    stable_locator: bool
    accountable_publisher: bool
    primary_source: bool
    policy_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _token(self.source_id, "source_id"))
        try:
            object.__setattr__(self, "source_class", SourceClass(self.source_class))
        except ValueError as exc:
            raise EvidencePlaneError("invalid source_class") from exc
        object.__setattr__(
            self,
            "quality_score",
            _unit(self.quality_score, "quality_score"),
        )
        for field in (
            "provenance_verified",
            "stable_locator",
            "accountable_publisher",
            "primary_source",
        ):
            if not isinstance(getattr(self, field), bool):
                raise EvidencePlaneError(f"{field} must be boolean")
        object.__setattr__(self, "policy_ref", _token(self.policy_ref, "policy_ref"))
        if self.source_class is SourceClass.PRIMARY and not self.primary_source:
            raise EvidencePlaneError(
                "primary source class requires primary_source=true"
            )
        if self.source_class is SourceClass.GENERATED and self.primary_source:
            raise EvidencePlaneError(
                "generated source cannot claim primary_source=true"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_class": self.source_class.value,
            "quality_score": self.quality_score,
            "provenance_verified": self.provenance_verified,
            "stable_locator": self.stable_locator,
            "accountable_publisher": self.accountable_publisher,
            "primary_source": self.primary_source,
            "policy_ref": self.policy_ref,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ClaimPublicationPolicy:
    """Fail-closed publication requirements for one claim class."""

    policy_id: str
    min_source_quality: float = 0.65
    min_supporting_origins: int = 1
    min_high_risk_origins: int = 2
    require_primary_for_high_risk: bool = True
    require_provenance_refs: bool = True
    require_stable_locator: bool = True
    require_accountable_publisher: bool = False
    requires_current_evidence: bool = False
    max_evidence_age_s: float | None = None
    allow_qualified_independence_shortfall: bool = False
    schema_version: int = EVIDENCE_CITATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "min_source_quality",
            _unit(self.min_source_quality, "min_source_quality"),
        )
        object.__setattr__(
            self,
            "min_supporting_origins",
            _positive_int(self.min_supporting_origins, "min_supporting_origins"),
        )
        object.__setattr__(
            self,
            "min_high_risk_origins",
            _positive_int(self.min_high_risk_origins, "min_high_risk_origins"),
        )
        for field in (
            "require_primary_for_high_risk",
            "require_provenance_refs",
            "require_stable_locator",
            "require_accountable_publisher",
            "requires_current_evidence",
            "allow_qualified_independence_shortfall",
        ):
            if not isinstance(getattr(self, field), bool):
                raise EvidencePlaneError(f"{field} must be boolean")
        if self.max_evidence_age_s is not None:
            object.__setattr__(
                self,
                "max_evidence_age_s",
                _finite(
                    self.max_evidence_age_s,
                    "max_evidence_age_s",
                    minimum=0.0,
                ),
            )
        if self.requires_current_evidence and self.max_evidence_age_s is None:
            raise EvidencePlaneError(
                "current-evidence policy requires max_evidence_age_s"
            )
        if self.schema_version != EVIDENCE_CITATION_SCHEMA_VERSION:
            raise EvidencePlaneError("unsupported publication policy schema")

    def required_origins(self, risk: VerificationRisk) -> int:
        if risk in {VerificationRisk.HIGH, VerificationRisk.CRITICAL}:
            return max(self.min_supporting_origins, self.min_high_risk_origins)
        return self.min_supporting_origins

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "min_source_quality": self.min_source_quality,
            "min_supporting_origins": self.min_supporting_origins,
            "min_high_risk_origins": self.min_high_risk_origins,
            "require_primary_for_high_risk": self.require_primary_for_high_risk,
            "require_provenance_refs": self.require_provenance_refs,
            "require_stable_locator": self.require_stable_locator,
            "require_accountable_publisher": self.require_accountable_publisher,
            "requires_current_evidence": self.requires_current_evidence,
            "max_evidence_age_s": self.max_evidence_age_s,
            "allow_qualified_independence_shortfall":
                self.allow_qualified_independence_shortfall,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ClaimEvidenceBundle:
    evidence: EvidenceReference
    citation: CitationBinding
    source: SourceQualityProfile

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, EvidenceReference):
            raise TypeError("evidence must be EvidenceReference")
        if not isinstance(self.citation, CitationBinding):
            raise TypeError("citation must be CitationBinding")
        if not isinstance(self.source, SourceQualityProfile):
            raise TypeError("source must be SourceQualityProfile")

    def as_dict(self) -> dict[str, object]:
        citation = {
            "claim": self.citation.claim,
            "source_id": self.citation.source_id,
            "locator": self.citation.locator,
            "binding_method": self.citation.binding_method,
            "evidence_span": self.citation.evidence_span,
            "supports": self.citation.supports,
            "provenance_verified": self.citation.provenance_verified,
            "source_content_sha256": self.citation.source_content_sha256,
            "mapping_rationale": self.citation.mapping_rationale,
        }
        return {
            "evidence": self.evidence.as_dict(),
            "citation": citation,
            "source": self.source.as_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    evidence_id: str
    bundle_digest: str
    relation: EvidenceRelation | str
    authoritative: bool
    eligible: bool
    reasons: tuple[str, ...]
    citation_attestation_sha256: str
    source_profile_digest: str
    age_s: float
    quality_score: float
    origin_id: str
    primary_source: bool

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "relation", EvidenceRelation(self.relation))
        except ValueError as exc:
            raise EvidencePlaneError("invalid evidence assessment relation") from exc
        object.__setattr__(self, "bundle_digest", _sha(self.bundle_digest, "bundle_digest"))
        object.__setattr__(
            self,
            "citation_attestation_sha256",
            _sha(
                self.citation_attestation_sha256,
                "citation_attestation_sha256",
            ),
        )
        object.__setattr__(
            self,
            "source_profile_digest",
            _sha(self.source_profile_digest, "source_profile_digest"),
        )
        if not isinstance(self.authoritative, bool) or not isinstance(self.eligible, bool):
            raise EvidencePlaneError("assessment authority flags must be boolean")
        if self.eligible and not self.authoritative:
            raise EvidencePlaneError("eligible evidence must be authoritative")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise EvidencePlaneError("assessment reasons must be strings")
        object.__setattr__(self, "age_s", _finite(self.age_s, "age_s", minimum=0.0))
        object.__setattr__(
            self,
            "quality_score",
            _unit(self.quality_score, "quality_score"),
        )
        if not isinstance(self.primary_source, bool):
            raise EvidencePlaneError("primary_source must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "bundle_digest": self.bundle_digest,
            "relation": self.relation.value,
            "authoritative": self.authoritative,
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "citation_attestation_sha256": self.citation_attestation_sha256,
            "source_profile_digest": self.source_profile_digest,
            "age_s": self.age_s,
            "quality_score": self.quality_score,
            "origin_id": self.origin_id,
            "primary_source": self.primary_source,
        }


@dataclass(frozen=True, slots=True)
class ClaimEvidenceReceipt:
    claim_id: str
    claim_digest: str
    claim_identity_sha256: str
    policy_digest: str
    disposition: PublicationDisposition | str
    reasons: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    context_evidence_ids: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]
    supporting_origin_ids: tuple[str, ...]
    assessments: tuple[EvidenceAssessment, ...]
    evaluated_at: datetime
    schema_version: int = EVIDENCE_CITATION_SCHEMA_VERSION
    authority_scope: str = "evidence-publication-eligibility-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "disposition",
                PublicationDisposition(self.disposition),
            )
        except ValueError as exc:
            raise EvidencePlaneError("invalid publication disposition") from exc
        object.__setattr__(self, "claim_digest", _sha(self.claim_digest, "claim_digest"))
        object.__setattr__(
            self,
            "claim_identity_sha256",
            _sha(self.claim_identity_sha256, "claim_identity_sha256"),
        )
        object.__setattr__(self, "policy_digest", _sha(self.policy_digest, "policy_digest"))
        object.__setattr__(self, "evaluated_at", _utc(self.evaluated_at, "evaluated_at"))
        if self.authority_scope != "evidence-publication-eligibility-only":
            raise EvidencePlaneError("evidence receipt authority scope escalated")
        if self.production_authority is not False:
            raise EvidencePlaneError("evidence receipt cannot publish or execute")
        if self.schema_version != EVIDENCE_CITATION_SCHEMA_VERSION:
            raise EvidencePlaneError("unsupported evidence receipt schema")
        if self.disposition is PublicationDisposition.PUBLISH:
            if not self.supporting_evidence_ids or self.contradicting_evidence_ids:
                raise EvidencePlaneError(
                    "publish disposition requires support and no contradiction"
                )
        if self.disposition is PublicationDisposition.CONTESTED:
            if not self.contradicting_evidence_ids:
                raise EvidencePlaneError(
                    "contested disposition requires contradiction"
                )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "claim_digest": self.claim_digest,
            "claim_identity_sha256": self.claim_identity_sha256,
            "policy_digest": self.policy_digest,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "context_evidence_ids": list(self.context_evidence_ids),
            "rejected_evidence_ids": list(self.rejected_evidence_ids),
            "supporting_origin_ids": list(self.supporting_origin_ids),
            "assessments": [item.as_dict() for item in self.assessments],
            "evaluated_at": self.evaluated_at.isoformat(),
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class EvidenceCitationPlane:
    """Deterministic claim-evidence admission and publication eligibility."""

    def __init__(self) -> None:
        self._citation = CitationIntegrityEngine()
        self._identity = ClaimIdentityEngine()

    def _assess(
        self,
        *,
        claim: VerificationClaim,
        bundle: ClaimEvidenceBundle,
        policy: ClaimPublicationPolicy,
        evaluated_at: datetime,
        duplicate: bool,
    ) -> EvidenceAssessment:
        evidence = bundle.evidence
        citation = bundle.citation
        source = bundle.source
        reasons: list[str] = []

        reference_result = validate_reference(claim, evidence)
        reasons.extend(reference_result.reasons)

        if source.source_id != evidence.source_id:
            reasons.append("source_profile_identity_mismatch")
        if citation.source_id != evidence.source_id:
            reasons.append("citation_source_identity_mismatch")
        if citation.locator != evidence.locator:
            reasons.append("citation_locator_mismatch")
        if citation.source_content_sha256 != evidence.content_digest:
            reasons.append("citation_content_digest_mismatch")

        try:
            identity = self._identity.compare(claim.text, citation.claim)
        except ValueError:
            reasons.append("citation_claim_missing")
        else:
            if not identity.identity_equal:
                reasons.append("citation_claim_identity_mismatch")

        if evidence.relation is EvidenceRelation.SUPPORTS and not citation.supports:
            reasons.append("citation_relation_mismatch")
        elif (
            evidence.relation is EvidenceRelation.CONTRADICTS
            and citation.supports
        ):
            reasons.append("citation_relation_mismatch")

        citation_report = self._citation.validate(citation)
        if not citation_report.accepted:
            reasons.extend(
                "citation_integrity:" + reason
                for reason in citation_report.reasons
            )

        if duplicate:
            reasons.append("duplicate_evidence_id")
        if not source.provenance_verified:
            reasons.append("source_profile_provenance_unverified")
        if not citation.provenance_verified:
            reasons.append("citation_provenance_unverified")
        if policy.require_provenance_refs and not evidence.provenance_refs:
            reasons.append("evidence_provenance_refs_missing")
        if policy.require_stable_locator and not source.stable_locator:
            reasons.append("source_locator_not_stable")
        if (
            policy.require_accountable_publisher
            and not source.accountable_publisher
        ):
            reasons.append("source_publisher_not_accountable")
        if source.quality_score < policy.min_source_quality:
            reasons.append("source_quality_below_policy")

        now = _utc(evaluated_at, "evaluated_at")
        if evidence.observed_at > now:
            age_s = 0.0
            reasons.append("evidence_observed_in_future")
        else:
            age_s = (now - evidence.observed_at).total_seconds()
        if (
            policy.requires_current_evidence
            and policy.max_evidence_age_s is not None
            and age_s > policy.max_evidence_age_s
        ):
            reasons.append("evidence_stale_for_current_claim")

        authoritative = (
            reference_result.authoritative
            and source.provenance_verified
            and citation.provenance_verified
            and source.source_class is not SourceClass.GENERATED
            and evidence.producer is not EvidenceProducer.MODEL
        )
        if not authoritative:
            reasons.append("evidence_non_authoritative")

        eligible = authoritative and not reasons
        return EvidenceAssessment(
            evidence_id=evidence.evidence_id,
            bundle_digest=bundle.digest,
            relation=evidence.relation,
            authoritative=authoritative,
            eligible=eligible,
            reasons=tuple(sorted(set(reasons))),
            citation_attestation_sha256=citation_report.attestation_sha256,
            source_profile_digest=source.digest,
            age_s=age_s,
            quality_score=source.quality_score,
            origin_id=evidence.origin_id,
            primary_source=source.primary_source,
        )

    def evaluate(
        self,
        *,
        claim: VerificationClaim,
        bundles: Sequence[ClaimEvidenceBundle] | Iterable[ClaimEvidenceBundle],
        policy: ClaimPublicationPolicy,
        evaluated_at: datetime,
    ) -> ClaimEvidenceReceipt:
        if not isinstance(claim, VerificationClaim):
            raise TypeError("claim must be VerificationClaim")
        if not isinstance(policy, ClaimPublicationPolicy):
            raise TypeError("policy must be ClaimPublicationPolicy")
        now = _utc(evaluated_at, "evaluated_at")
        values = tuple(bundles)
        if any(not isinstance(item, ClaimEvidenceBundle) for item in values):
            raise TypeError("bundles must contain ClaimEvidenceBundle")

        seen: set[str] = set()
        assessments: list[EvidenceAssessment] = []
        for bundle in values:
            evidence_id = bundle.evidence.evidence_id
            duplicate = evidence_id in seen
            seen.add(evidence_id)
            assessments.append(
                self._assess(
                    claim=claim,
                    bundle=bundle,
                    policy=policy,
                    evaluated_at=now,
                    duplicate=duplicate,
                )
            )

        supporting: list[str] = []
        contradicting: list[str] = []
        context: list[str] = []
        rejected: list[str] = []
        origins: list[str] = []
        primary_support = False

        classified_ids: set[str] = set()
        for item in assessments:
            if not item.eligible:
                # A replayed duplicate assessment can be rejected while the
                # original immutable evidence identity remains legitimately
                # classified. Do not make the final receipt contradictory by
                # placing one evidence_id in both accepted and rejected sets.
                if item.evidence_id not in classified_ids and item.evidence_id not in rejected:
                    rejected.append(item.evidence_id)
                continue
            classified_ids.add(item.evidence_id)
            if item.evidence_id in rejected:
                rejected.remove(item.evidence_id)
            if item.relation is EvidenceRelation.SUPPORTS:
                if item.evidence_id not in supporting:
                    supporting.append(item.evidence_id)
                if item.origin_id not in origins:
                    origins.append(item.origin_id)
                primary_support = primary_support or item.primary_source
            elif item.relation is EvidenceRelation.CONTRADICTS:
                if item.evidence_id not in contradicting:
                    contradicting.append(item.evidence_id)
            else:
                if item.evidence_id not in context:
                    context.append(item.evidence_id)

        reasons: list[str] = []
        required_origins = policy.required_origins(claim.risk)

        if contradicting:
            disposition = PublicationDisposition.CONTESTED
            reasons.append("authoritative_contradiction_present")
        elif not supporting:
            disposition = PublicationDisposition.ABSTAIN
            reasons.append("no_authoritative_support")
        elif (
            claim.risk in {VerificationRisk.HIGH, VerificationRisk.CRITICAL}
            and policy.require_primary_for_high_risk
            and not primary_support
        ):
            disposition = PublicationDisposition.ABSTAIN
            reasons.append("high_risk_claim_requires_primary_source")
        elif len(origins) < required_origins:
            reasons.append("independent_origin_requirement_not_met")
            if policy.allow_qualified_independence_shortfall:
                disposition = PublicationDisposition.PUBLISH_WITH_QUALIFICATION
            else:
                disposition = PublicationDisposition.ABSTAIN
        else:
            disposition = PublicationDisposition.PUBLISH

        claim_identity = self._identity.canonical_id(claim.text)
        return ClaimEvidenceReceipt(
            claim_id=claim.claim_id,
            claim_digest=claim.digest,
            claim_identity_sha256=claim_identity,
            policy_digest=policy.digest,
            disposition=disposition,
            reasons=tuple(reasons),
            supporting_evidence_ids=tuple(supporting),
            contradicting_evidence_ids=tuple(contradicting),
            context_evidence_ids=tuple(context),
            rejected_evidence_ids=tuple(rejected),
            supporting_origin_ids=tuple(origins),
            assessments=tuple(assessments),
            evaluated_at=now,
        )


__all__ = [
    "EVIDENCE_CITATION_SCHEMA_VERSION",
    "ClaimEvidenceBundle",
    "ClaimEvidenceReceipt",
    "ClaimPublicationPolicy",
    "EvidenceAssessment",
    "EvidenceCitationPlane",
    "EvidencePlaneError",
    "PublicationDisposition",
    "SourceClass",
    "SourceQualityProfile",
]
