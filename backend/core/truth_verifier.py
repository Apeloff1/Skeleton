"""Empirical truth verifier for the Curiosity/Jeeves knowledge fabric.

Design doctrine
---------------
* Truth is evidence-bound, never model-consensus-bound.
* Repetition, confidence wording, majority vote, or model agreement do not count
  as empirical verification.
* Every verified claim must have inspectable provenance and pass scientific
  quality gates: source independence, reproducibility/replicability signal,
  falsifiability, contradiction review, temporal validity, and evidence quality.
* Uncertainty/speculation remains available to HOAG as an auditable hypothesis or
  gap, but is irrelevant to the verified-knowledge projection until evidence
  promotes it.
* Unknown is preferred over invented certainty.

This module does not promise metaphysical certainty. "verified" means the claim
meets the configured empirical standard given the supplied evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping


class VerificationState(StrEnum):
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    SPECULATION = "irrelevant_speculation"


class EvidenceKind(StrEnum):
    PRIMARY_EMPIRICAL = "primary_empirical"
    REPLICATION = "replication"
    SYSTEMATIC_REVIEW = "systematic_review"
    OFFICIAL_DATA = "official_data"
    PRIMARY_DOCUMENT = "primary_document"
    DIRECT_OBSERVATION = "direct_observation"
    SECONDARY_ANALYSIS = "secondary_analysis"
    EXPERT_SUMMARY = "expert_summary"
    MODEL_OBSERVATION = "model_observation"
    UNSOURCED = "unsourced"


_EMPIRICAL_KINDS = {
    EvidenceKind.PRIMARY_EMPIRICAL,
    EvidenceKind.REPLICATION,
    EvidenceKind.SYSTEMATIC_REVIEW,
    EvidenceKind.OFFICIAL_DATA,
    EvidenceKind.PRIMARY_DOCUMENT,
    EvidenceKind.DIRECT_OBSERVATION,
}

_NON_EVIDENCE_KINDS = {EvidenceKind.MODEL_OBSERVATION, EvidenceKind.UNSOURCED}


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    source_id: str
    locator: str
    kind: EvidenceKind
    supports: bool
    independence_group: str
    quality: float
    observed_at: str = ""
    reproducible: bool = False
    peer_reviewed: bool = False
    primary: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    minimum_independent_support: int = 2
    minimum_total_quality: float = 1.35
    minimum_mean_quality: float = 0.60
    require_empirical_support: bool = True
    require_reproducibility_signal: bool = True
    require_falsifiable_claim: bool = True
    contradiction_blocks: bool = True
    max_source_age_days: int | None = None
    provisional_independent_support: int = 1


@dataclass(frozen=True, slots=True)
class ClaimVerification:
    claim: str
    state: VerificationState
    empirical_support: int
    independent_support: int
    independent_contradictions: int
    total_quality: float
    mean_quality: float
    reproducibility_signal: bool
    falsifiable: bool
    reasons: tuple[str, ...]
    accepted_evidence: tuple[EvidenceItem, ...]
    rejected_evidence: tuple[EvidenceItem, ...]
    attestation_sha256: str


@dataclass(frozen=True, slots=True)
class VerificationBatch:
    verified: tuple[ClaimVerification, ...]
    provisional: tuple[ClaimVerification, ...]
    irrelevant_speculation: tuple[ClaimVerification, ...]
    contradicted: tuple[ClaimVerification, ...]
    unverified: tuple[ClaimVerification, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite_score(value: float, *, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


def _age_days(stamp: str, now: datetime) -> float | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    return max(0.0, (now - when.astimezone(UTC)).total_seconds() / 86400.0)


def _looks_falsifiable(claim: str) -> bool:
    """Conservative syntactic guard; callers can explicitly override by evidence design.

    The aim is hallucination resistance, not philosophy automation. Empty/vague,
    purely normative, supernatural, or self-sealing statements cannot become
    VERIFIED through this engine.
    """
    text = " ".join(claim.split()).strip()
    if len(text) < 8:
        return False
    lowered = text.casefold()
    vague = (
        "everyone knows", "obviously", "undeniably", "always true", "cannot be tested",
        "beyond measurement", "because i feel", "must be true", "probably somehow",
    )
    if any(token in lowered for token in vague):
        return False
    # Claims with a measurable relation, quantity, event, comparison, causal or
    # categorical assertion are potentially falsifiable.
    measurable = re.search(r"\b(is|are|was|were|causes?|increases?|decreases?|predicts?|contains?|occurred|measured|equals?|greater|less|associated|correlat)\b", lowered)
    numeric = re.search(r"\d", lowered)
    return bool(measurable or numeric)


def _evidence_payload(item: EvidenceItem) -> dict[str, Any]:
    data = asdict(item)
    data["kind"] = item.kind.value
    return data


class TruthVerifier:
    def __init__(self, policy: VerificationPolicy | None = None) -> None:
        self.policy = policy or VerificationPolicy()
        if self.policy.minimum_independent_support < 1:
            raise ValueError("minimum_independent_support must be >= 1")
        if self.policy.provisional_independent_support < 1:
            raise ValueError("provisional_independent_support must be >= 1")

    def verify_claim(
        self,
        claim: str,
        evidence: Iterable[EvidenceItem],
        *,
        falsifiable: bool | None = None,
        now: datetime | None = None,
    ) -> ClaimVerification:
        claim = " ".join(str(claim).split()).strip()
        if not claim:
            raise ValueError("claim cannot be blank")
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("verification time must be timezone-aware")
        claim_falsifiable = _looks_falsifiable(claim) if falsifiable is None else bool(falsifiable)

        accepted: list[EvidenceItem] = []
        rejected: list[EvidenceItem] = []
        reasons: list[str] = []
        for raw in evidence:
            item = replace(raw, quality=_finite_score(raw.quality, name="evidence quality"))
            if not item.source_id.strip() or not item.independence_group.strip():
                rejected.append(item); continue
            if item.kind in _NON_EVIDENCE_KINDS:
                rejected.append(item); continue
            age = _age_days(item.observed_at, now)
            if self.policy.max_source_age_days is not None and age is not None and age > self.policy.max_source_age_days:
                rejected.append(item); continue
            accepted.append(item)

        support = [e for e in accepted if e.supports]
        contradictions = [e for e in accepted if not e.supports]
        support_groups = {e.independence_group for e in support}
        contradiction_groups = {e.independence_group for e in contradictions}
        empirical_support = sum(1 for e in support if e.kind in _EMPIRICAL_KINDS)
        total_quality = sum(e.quality for e in support)
        mean_quality = total_quality / len(support) if support else 0.0
        reproducible = any(e.reproducible or e.kind == EvidenceKind.REPLICATION for e in support)

        if self.policy.require_falsifiable_claim and not claim_falsifiable:
            reasons.append("claim_not_falsifiable")
        if self.policy.require_empirical_support and empirical_support == 0:
            reasons.append("no_empirical_support")
        if len(support_groups) < self.policy.minimum_independent_support:
            reasons.append("insufficient_independent_support")
        if total_quality < self.policy.minimum_total_quality:
            reasons.append("insufficient_total_evidence_quality")
        if mean_quality < self.policy.minimum_mean_quality:
            reasons.append("insufficient_mean_evidence_quality")
        if self.policy.require_reproducibility_signal and not reproducible:
            reasons.append("no_reproducibility_signal")
        if contradiction_groups:
            reasons.append("contradictory_empirical_evidence")

        if contradictions and self.policy.contradiction_blocks:
            state = VerificationState.CONTRADICTED
        elif not support and not accepted:
            # Pure model observation / unsourced assertion is explicitly irrelevant
            # to verified knowledge regardless of how confidently it was stated.
            state = VerificationState.SPECULATION
            reasons.append("speculation_is_not_evidence")
        elif not reasons:
            state = VerificationState.VERIFIED
        elif (
            empirical_support >= 1
            and len(support_groups) >= self.policy.provisional_independent_support
            and not contradiction_groups
            and claim_falsifiable
        ):
            state = VerificationState.PROVISIONAL
        else:
            state = VerificationState.UNVERIFIED

        payload = {
            "claim": claim,
            "state": state.value,
            "empirical_support": empirical_support,
            "independent_support": len(support_groups),
            "independent_contradictions": len(contradiction_groups),
            "total_quality": round(total_quality, 6),
            "mean_quality": round(mean_quality, 6),
            "reproducibility_signal": reproducible,
            "falsifiable": claim_falsifiable,
            "reasons": tuple(dict.fromkeys(reasons)),
            "accepted_evidence": tuple(_evidence_payload(e) for e in accepted),
            "rejected_evidence": tuple(_evidence_payload(e) for e in rejected),
        }
        return ClaimVerification(
            claim=claim, state=state, empirical_support=empirical_support,
            independent_support=len(support_groups), independent_contradictions=len(contradiction_groups),
            total_quality=round(total_quality, 6), mean_quality=round(mean_quality, 6),
            reproducibility_signal=reproducible, falsifiable=claim_falsifiable,
            reasons=tuple(dict.fromkeys(reasons)), accepted_evidence=tuple(accepted),
            rejected_evidence=tuple(rejected), attestation_sha256=_digest(payload),
        )

    def verify_many(
        self,
        claims: Iterable[str],
        evidence_by_claim: Mapping[str, Iterable[EvidenceItem]],
        *,
        falsifiability: Mapping[str, bool] | None = None,
    ) -> VerificationBatch:
        results = [
            self.verify_claim(
                claim,
                evidence_by_claim.get(claim, ()),
                falsifiable=(falsifiability or {}).get(claim),
            )
            for claim in claims
        ]
        verified = tuple(x for x in results if x.state == VerificationState.VERIFIED)
        provisional = tuple(x for x in results if x.state == VerificationState.PROVISIONAL)
        speculation = tuple(x for x in results if x.state == VerificationState.SPECULATION)
        contradicted = tuple(x for x in results if x.state == VerificationState.CONTRADICTED)
        unverified = tuple(x for x in results if x.state == VerificationState.UNVERIFIED)
        payload = {
            "verified": [x.attestation_sha256 for x in verified],
            "provisional": [x.attestation_sha256 for x in provisional],
            "irrelevant_speculation": [x.attestation_sha256 for x in speculation],
            "contradicted": [x.attestation_sha256 for x in contradicted],
            "unverified": [x.attestation_sha256 for x in unverified],
        }
        return VerificationBatch(verified, provisional, speculation, contradicted, unverified, _digest(payload))

    @staticmethod
    def verified_projection(batch: VerificationBatch) -> tuple[str, ...]:
        """Only empirically verified claims enter the authoritative projection."""
        return tuple(item.claim for item in batch.verified)

    @staticmethod
    def epistemic_projection(batch: VerificationBatch) -> dict[str, Any]:
        return {
            "verified": [item.claim for item in batch.verified],
            "provisional": [item.claim for item in batch.provisional],
            "contradicted": [item.claim for item in batch.contradicted],
            "unverified": [item.claim for item in batch.unverified],
            "irrelevant_speculation": [item.claim for item in batch.irrelevant_speculation],
            "attestation_sha256": batch.attestation_sha256,
        }


def verify_claim_attestation(result: ClaimVerification) -> bool:
    payload = {
        "claim": result.claim,
        "state": result.state.value,
        "empirical_support": result.empirical_support,
        "independent_support": result.independent_support,
        "independent_contradictions": result.independent_contradictions,
        "total_quality": result.total_quality,
        "mean_quality": result.mean_quality,
        "reproducibility_signal": result.reproducibility_signal,
        "falsifiable": result.falsifiable,
        "reasons": result.reasons,
        "accepted_evidence": tuple(_evidence_payload(e) for e in result.accepted_evidence),
        "rejected_evidence": tuple(_evidence_payload(e) for e in result.rejected_evidence),
    }
    return _digest(payload) == result.attestation_sha256
