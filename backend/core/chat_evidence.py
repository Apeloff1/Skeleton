"""Claim-level evidence acceptance for AI-chat responses.

This plane composes the repository's citation-integrity engine with explicit
freshness, source-quality, authority, independence, and conflict requirements.
It does not retrieve sources and it does not mutate the durable evidence
registry. Its output is a deterministic acceptance receipt for response
verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Iterable

from core.citation_integrity import (
    CitationBinding,
    CitationIntegrityEngine,
    CitationIntegrityReport,
)


class ChatEvidenceError(ValueError):
    """Evidence cannot be evaluated under the requested policy."""


class EvidenceRequirement(str, Enum):
    SYNTHESIS_ONLY = "synthesis_only"
    EVIDENCE_SUPPORTED = "evidence_supported"
    FRESHNESS_REQUIRED = "freshness_required"
    AUTHORITATIVE_SOURCE_REQUIRED = "authoritative_source_required"
    HIGH_ASSURANCE = "high_assurance"


class SourceClass(str, Enum):
    AUTHORITATIVE = "authoritative"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ChatEvidenceError(
            "evidence receipt is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite_unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChatEvidenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ChatEvidenceError(f"{name} must be within [0,1]")
    return number


def _finite_nonnegative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChatEvidenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ChatEvidenceError(
            f"{name} must be finite and non-negative"
        )
    return number


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    requirement: EvidenceRequirement
    min_supporting_sources: int = 1
    min_independence_groups: int = 1
    min_quality: float = 0.0
    max_age_s: float | None = None
    allowed_source_classes: frozenset[SourceClass] = frozenset(SourceClass)
    reject_on_conflict: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, EvidenceRequirement):
            object.__setattr__(
                self,
                "requirement",
                EvidenceRequirement(str(self.requirement)),
            )
        for name in ("min_supporting_sources", "min_independence_groups"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ChatEvidenceError(
                    f"{name} must be a non-negative integer"
                )
        object.__setattr__(
            self,
            "min_quality",
            _finite_unit(self.min_quality, "min_quality"),
        )
        if self.max_age_s is not None:
            object.__setattr__(
                self,
                "max_age_s",
                _finite_nonnegative(self.max_age_s, "max_age_s"),
            )
        classes = frozenset(
            value
            if isinstance(value, SourceClass)
            else SourceClass(str(value))
            for value in self.allowed_source_classes
        )
        if not classes:
            raise ChatEvidenceError(
                "allowed_source_classes must not be empty"
            )
        object.__setattr__(
            self,
            "allowed_source_classes",
            classes,
        )
        if not isinstance(self.reject_on_conflict, bool):
            raise ChatEvidenceError(
                "reject_on_conflict must be boolean"
            )

        if self.requirement is EvidenceRequirement.SYNTHESIS_ONLY:
            if self.min_supporting_sources != 0:
                object.__setattr__(
                    self,
                    "min_supporting_sources",
                    0,
                )
            if self.min_independence_groups != 0:
                object.__setattr__(
                    self,
                    "min_independence_groups",
                    0,
                )
        if (
            self.requirement
            in {
                EvidenceRequirement.FRESHNESS_REQUIRED,
                EvidenceRequirement.HIGH_ASSURANCE,
            }
            and self.max_age_s is None
        ):
            raise ChatEvidenceError(
                "freshness-required policy must set max_age_s"
            )
        if (
            self.requirement
            in {
                EvidenceRequirement.AUTHORITATIVE_SOURCE_REQUIRED,
                EvidenceRequirement.HIGH_ASSURANCE,
            }
            and not self.allowed_source_classes
            <= {
                SourceClass.AUTHORITATIVE,
                SourceClass.PRIMARY,
            }
        ):
            raise ChatEvidenceError(
                "authoritative-source policy may allow only authoritative or primary sources"
            )

    @classmethod
    def for_requirement(
        cls,
        requirement: EvidenceRequirement,
    ) -> "EvidencePolicy":
        requirement = (
            requirement
            if isinstance(requirement, EvidenceRequirement)
            else EvidenceRequirement(str(requirement))
        )
        if requirement is EvidenceRequirement.SYNTHESIS_ONLY:
            return cls(
                requirement,
                min_supporting_sources=0,
                min_independence_groups=0,
                reject_on_conflict=False,
            )
        if requirement is EvidenceRequirement.EVIDENCE_SUPPORTED:
            return cls(
                requirement,
                min_supporting_sources=1,
                min_independence_groups=1,
                min_quality=0.4,
            )
        if requirement is EvidenceRequirement.FRESHNESS_REQUIRED:
            return cls(
                requirement,
                min_supporting_sources=1,
                min_independence_groups=1,
                min_quality=0.4,
                max_age_s=3600.0,
            )
        if requirement is EvidenceRequirement.AUTHORITATIVE_SOURCE_REQUIRED:
            return cls(
                requirement,
                min_supporting_sources=1,
                min_independence_groups=1,
                min_quality=0.6,
                allowed_source_classes=frozenset(
                    {
                        SourceClass.AUTHORITATIVE,
                        SourceClass.PRIMARY,
                    }
                ),
            )
        return cls(
            requirement,
            min_supporting_sources=2,
            min_independence_groups=2,
            min_quality=0.7,
            max_age_s=3600.0,
            allowed_source_classes=frozenset(
                {
                    SourceClass.AUTHORITATIVE,
                    SourceClass.PRIMARY,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    source_id: str
    locator: str
    evidence_span: str
    binding_method: str
    supports: bool
    provenance_verified: bool
    source_content_sha256: str
    source_class: SourceClass
    quality: float
    independence_group: str
    observed_at: float | None = None
    mapping_rationale: str = ""

    def __post_init__(self) -> None:
        for name in (
            "source_id",
            "locator",
            "evidence_span",
            "binding_method",
            "source_content_sha256",
            "independence_group",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ChatEvidenceError(
                    f"{name} must be non-empty text"
                )
            object.__setattr__(self, name, value.strip())
        digest = self.source_content_sha256.lower()
        if len(digest) != 64 or any(
            char not in "0123456789abcdef"
            for char in digest
        ):
            raise ChatEvidenceError(
                "source_content_sha256 must be lowercase sha256"
            )
        object.__setattr__(
            self,
            "source_content_sha256",
            digest,
        )
        if not isinstance(self.source_class, SourceClass):
            object.__setattr__(
                self,
                "source_class",
                SourceClass(str(self.source_class)),
            )
        object.__setattr__(
            self,
            "quality",
            _finite_unit(self.quality, "quality"),
        )
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                _finite_nonnegative(
                    self.observed_at,
                    "observed_at",
                ),
            )
        if not isinstance(self.supports, bool):
            raise ChatEvidenceError("supports must be boolean")
        if not isinstance(self.provenance_verified, bool):
            raise ChatEvidenceError(
                "provenance_verified must be boolean"
            )


@dataclass(frozen=True, slots=True)
class AcceptedCitation:
    source_id: str
    locator: str
    source_class: SourceClass
    supports: bool
    quality: float
    independence_group: str
    citation_attestation_sha256: str
    age_s: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "source_class": self.source_class.value,
            "supports": self.supports,
            "quality": self.quality,
            "independence_group": self.independence_group,
            "citation_attestation_sha256":
                self.citation_attestation_sha256,
            "age_s": self.age_s,
        }


@dataclass(frozen=True, slots=True)
class ClaimEvidenceDecision:
    claim: str
    accepted: bool
    requirement: EvidenceRequirement
    citations: tuple[AcceptedCitation, ...]
    rejected_sources: tuple[tuple[str, tuple[str, ...]], ...]
    reasons: tuple[str, ...]
    evaluated_at: float
    digest: str

    def __post_init__(self) -> None:
        payload = {
            "claim": self.claim,
            "accepted": self.accepted,
            "requirement": self.requirement.value,
            "citations": [
                citation.as_dict()
                for citation in self.citations
            ],
            "rejected_sources": [
                [source, list(reasons)]
                for source, reasons in self.rejected_sources
            ],
            "reasons": list(self.reasons),
            "evaluated_at": self.evaluated_at,
        }
        if self.digest != _digest(payload):
            raise ChatEvidenceError(
                "claim evidence decision digest mismatch"
            )


class ChatEvidenceGate:
    def __init__(
        self,
        citation_engine: CitationIntegrityEngine | None = None,
    ) -> None:
        self.citation_engine = (
            citation_engine or CitationIntegrityEngine()
        )

    def evaluate(
        self,
        claim: str,
        candidates: Iterable[ClaimEvidence],
        *,
        policy: EvidencePolicy,
        now: float,
    ) -> ClaimEvidenceDecision:
        if not isinstance(claim, str) or not claim.strip():
            raise ChatEvidenceError(
                "claim must be non-empty text"
            )
        normalized_claim = " ".join(claim.split()).strip()
        if not isinstance(policy, EvidencePolicy):
            raise TypeError("policy must be EvidencePolicy")
        now_value = _finite_nonnegative(now, "now")

        accepted: list[AcceptedCitation] = []
        rejected: list[tuple[str, tuple[str, ...]]] = []
        for candidate in tuple(candidates):
            if not isinstance(candidate, ClaimEvidence):
                raise TypeError(
                    "candidates must contain ClaimEvidence values"
                )
            reasons: list[str] = []
            report: CitationIntegrityReport = (
                self.citation_engine.validate(
                    CitationBinding(
                        claim=normalized_claim,
                        source_id=candidate.source_id,
                        locator=candidate.locator,
                        binding_method=candidate.binding_method,
                        evidence_span=candidate.evidence_span,
                        supports=candidate.supports,
                        provenance_verified=candidate.provenance_verified,
                        source_content_sha256=
                            candidate.source_content_sha256,
                        mapping_rationale=
                            candidate.mapping_rationale,
                    )
                )
            )
            if not report.accepted:
                reasons.extend(
                    "citation:" + reason
                    for reason in report.reasons
                )
            if candidate.quality < policy.min_quality:
                reasons.append("source-quality-below-policy")
            if (
                candidate.source_class
                not in policy.allowed_source_classes
            ):
                reasons.append(
                    "source-class-not-allowed"
                )

            age_s: float | None = None
            if policy.max_age_s is not None:
                if candidate.observed_at is None:
                    reasons.append("freshness-metadata-missing")
                elif candidate.observed_at > now_value:
                    reasons.append(
                        "freshness-timestamp-in-future"
                    )
                else:
                    age_s = now_value - candidate.observed_at
                    if age_s > policy.max_age_s:
                        reasons.append(
                            "source-stale"
                        )

            if reasons:
                rejected.append(
                    (
                        candidate.source_id,
                        tuple(dict.fromkeys(reasons)),
                    )
                )
                continue
            accepted.append(
                AcceptedCitation(
                    source_id=candidate.source_id,
                    locator=candidate.locator,
                    source_class=candidate.source_class,
                    supports=candidate.supports,
                    quality=candidate.quality,
                    independence_group=
                        candidate.independence_group,
                    citation_attestation_sha256=
                        report.attestation_sha256,
                    age_s=age_s,
                )
            )

        support = tuple(
            citation
            for citation in accepted
            if citation.supports
        )
        contradictions = tuple(
            citation
            for citation in accepted
            if not citation.supports
        )
        reasons: list[str] = []
        if (
            len({item.source_id for item in support})
            < policy.min_supporting_sources
        ):
            reasons.append(
                "insufficient-supporting-sources"
            )
        if (
            len(
                {
                    item.independence_group
                    for item in support
                }
            )
            < policy.min_independence_groups
        ):
            reasons.append(
                "insufficient-independent-evidence"
            )
        if policy.reject_on_conflict and contradictions:
            reasons.append(
                "accepted-contradicting-evidence-present"
            )

        final_reasons = tuple(dict.fromkeys(reasons))
        final_citations = tuple(
            sorted(
                accepted,
                key=lambda item: (
                    not item.supports,
                    item.source_id,
                    item.locator,
                ),
            )
        )
        rejected_sources = tuple(
            sorted(
                rejected,
                key=lambda item: item[0],
            )
        )
        accepted_decision = not final_reasons
        payload = {
            "claim": normalized_claim,
            "accepted": accepted_decision,
            "requirement": policy.requirement.value,
            "citations": [
                citation.as_dict()
                for citation in final_citations
            ],
            "rejected_sources": [
                [source, list(source_reasons)]
                for source, source_reasons
                in rejected_sources
            ],
            "reasons": list(final_reasons),
            "evaluated_at": now_value,
        }
        return ClaimEvidenceDecision(
            claim=normalized_claim,
            accepted=accepted_decision,
            requirement=policy.requirement,
            citations=final_citations,
            rejected_sources=rejected_sources,
            reasons=final_reasons,
            evaluated_at=now_value,
            digest=_digest(payload),
        )


__all__ = [
    "AcceptedCitation",
    "ChatEvidenceError",
    "ChatEvidenceGate",
    "ClaimEvidence",
    "ClaimEvidenceDecision",
    "EvidencePolicy",
    "EvidenceRequirement",
    "SourceClass",
]
