"""Evidence-grounded cross-reference verification for dragon video research.

This module evaluates *corroboration*, not absolute truth. Claims are never
declared true merely because many copies of the same source agree. Independent
source families, contradicting evidence, freshness, and provenance are tracked.
No web requests or model calls occur here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
from urllib.parse import urlsplit
import json
import re

from .dragon_video_history import canonical_video_url


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    CONTEXT = "context"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    CONTESTED = "contested"
    CORROBORATED = "corroborated"
    REFUTED = "refuted"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    origin_url: str
    origin_time_ms: int | None = None


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    claim_id: str
    source_url: str
    source_family: str
    stance: EvidenceStance
    excerpt: str
    observed_at: float
    confidence: float
    primary: bool = False
    provenance_id: str = ""


@dataclass(frozen=True)
class VerificationPolicy:
    min_independent_sources: int = 2
    min_confidence: float = 0.65
    min_support_weight: float = 1.25
    contradiction_threshold: float = 0.65
    max_evidence: int = 256
    max_age_days: float = 365
    primary_weight: float = 1.25
    max_excerpt_chars: int = 1000


@dataclass(frozen=True)
class EvidenceAssessment:
    evidence_id: str
    source_family: str
    stance: EvidenceStance
    weight: float
    provenance_id: str


@dataclass(frozen=True)
class VerificationResult:
    claim_id: str
    status: VerificationStatus
    support_weight: float
    refutation_weight: float
    independent_supporters: int
    independent_refuters: int
    evidence: tuple[EvidenceAssessment, ...]
    rejected_evidence: int
    explanation: str
    fingerprint: str


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _validate_claim(claim: Claim) -> None:
    if not _ID.fullmatch(claim.claim_id):
        raise ValueError("invalid claim identifier")
    if not claim.text.strip() or len(claim.text) > 4000:
        raise ValueError("invalid claim text")
    canonical_video_url(claim.origin_url)
    if claim.origin_time_ms is not None and not 0 <= claim.origin_time_ms <= 86400000:
        raise ValueError("invalid origin timecode")


def _validate_policy(policy: VerificationPolicy) -> None:
    if not 2 <= policy.min_independent_sources <= 20:
        raise ValueError("at least two independent sources required")
    if not 1 <= policy.max_evidence <= 10000:
        raise ValueError("invalid evidence budget")
    if not 1 <= policy.max_excerpt_chars <= 10000:
        raise ValueError("invalid excerpt budget")
    for number in (policy.min_confidence, policy.min_support_weight,
                   policy.contradiction_threshold, policy.max_age_days,
                   policy.primary_weight):
        if not isfinite(number):
            raise ValueError("non-finite verification policy")
    if not (0 <= policy.min_confidence <= 1 and
            0 < policy.min_support_weight <= 100 and
            0 < policy.contradiction_threshold <= 100 and
            0 < policy.max_age_days <= 36500 and
            1 <= policy.primary_weight <= 5):
        raise ValueError("invalid verification policy")


def _validate_evidence(item: Evidence, claim: Claim, now: float,
                       policy: VerificationPolicy) -> bool:
    if not _ID.fullmatch(item.evidence_id) or item.claim_id != claim.claim_id:
        return False
    if not isinstance(item.stance, EvidenceStance):
        return False
    if not item.source_family or len(item.source_family) > 128:
        return False
    if not item.excerpt.strip() or len(item.excerpt) > policy.max_excerpt_chars:
        return False
    if len(item.provenance_id) > 128:
        return False
    if not isfinite(item.observed_at) or item.observed_at > now:
        return False
    if now - item.observed_at > policy.max_age_days * 86400:
        return False
    if not isfinite(item.confidence) or not 0 <= item.confidence <= 1:
        return False
    try:
        canonical_video_url(item.source_url)
    except (TypeError, ValueError):
        return False
    return True


def verify_claim(
    claim: Claim,
    evidence: tuple[Evidence, ...],
    *,
    now: float,
    policy: VerificationPolicy = VerificationPolicy(),
) -> VerificationResult:
    _validate_claim(claim)
    _validate_policy(policy)
    if not isfinite(now):
        raise ValueError("invalid verification time")
    if len(evidence) > policy.max_evidence:
        raise ValueError("evidence processing budget exceeded")

    # One provenance identity may not vote repeatedly. Reposts from the same
    # family also count as one independent source per stance.
    distinct: dict[str, Evidence] = {}
    rejected = 0
    for item in evidence:
        if not _validate_evidence(item, claim, now, policy):
            rejected += 1
            continue
        identity = item.provenance_id or canonical_video_url(item.source_url)
        previous = distinct.get(identity)
        if previous is None or (item.confidence, item.evidence_id) > (
            previous.confidence, previous.evidence_id
        ):
            distinct[identity] = item

    by_family: dict[tuple[str, EvidenceStance], EvidenceAssessment] = {}
    for item in distinct.values():
        if item.confidence < policy.min_confidence:
            rejected += 1
            continue
        weight = item.confidence * (policy.primary_weight if item.primary else 1.0)
        key = (item.source_family.casefold().strip(), item.stance)
        assessment = EvidenceAssessment(
            item.evidence_id, key[0], item.stance, round(weight, 6),
            item.provenance_id,
        )
        previous = by_family.get(key)
        if previous is None or (assessment.weight, assessment.evidence_id) > (
            previous.weight, previous.evidence_id
        ):
            by_family[key] = assessment

    assessments = tuple(sorted(by_family.values(),
        key=lambda a: (a.source_family, a.stance.value, a.evidence_id)))
    supporters = [a for a in assessments if a.stance is EvidenceStance.SUPPORTS]
    refuters = [a for a in assessments if a.stance is EvidenceStance.REFUTES]
    support = round(sum(a.weight for a in supporters), 6)
    refutation = round(sum(a.weight for a in refuters), 6)
    enough_support = (len(supporters) >= policy.min_independent_sources and
                      support >= policy.min_support_weight)
    enough_refutation = (len(refuters) >= policy.min_independent_sources and
                        refutation >= policy.min_support_weight)
    meaningful_refutation = refutation >= policy.contradiction_threshold
    meaningful_support = support >= policy.contradiction_threshold

    if enough_support and meaningful_refutation:
        status = VerificationStatus.CONTESTED
    elif enough_refutation and meaningful_support:
        status = VerificationStatus.CONTESTED
    elif enough_support:
        status = VerificationStatus.CORROBORATED
    elif enough_refutation:
        status = VerificationStatus.REFUTED
    elif supporters or refuters:
        status = VerificationStatus.INSUFFICIENT
    else:
        status = VerificationStatus.UNVERIFIED

    explanation = (
        f"{len(supporters)} independent supporting source families; "
        f"{len(refuters)} independent refuting source families. "
        f"Status describes evidence agreement, not guaranteed factual truth."
    )
    payload = {
        "claim_id": claim.claim_id,
        "status": status.value,
        "evidence": [
            (a.evidence_id, a.source_family, a.stance.value, a.weight,
             a.provenance_id) for a in assessments
        ],
        "rejected": rejected,
        "policy": (
            policy.min_independent_sources, policy.min_confidence,
            policy.min_support_weight, policy.contradiction_threshold,
        ),
    }
    fingerprint = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return VerificationResult(
        claim.claim_id, status, support, refutation,
        len(supporters), len(refuters), assessments,
        rejected, explanation, fingerprint,
    )
