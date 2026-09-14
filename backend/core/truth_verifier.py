"""Empirical truth verifier for Curiosity/Jeeves.

"Verified" is an evidence state, not a confidence adjective. Model agreement,
repetition and unsourced assertions never count as empirical evidence. Evidence
quality is derived from source class and inspectable methodology; caller-supplied
quality is only an upper request and is capped by what the evidence can justify.
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
    EvidenceKind.PRIMARY_EMPIRICAL, EvidenceKind.REPLICATION,
    EvidenceKind.SYSTEMATIC_REVIEW, EvidenceKind.OFFICIAL_DATA,
    EvidenceKind.PRIMARY_DOCUMENT, EvidenceKind.DIRECT_OBSERVATION,
}
_NON_EVIDENCE_KINDS = {EvidenceKind.MODEL_OBSERVATION, EvidenceKind.UNSOURCED}
_EXPERIMENTAL_KINDS = {EvidenceKind.PRIMARY_EMPIRICAL, EvidenceKind.REPLICATION}
_KIND_CEILINGS = {
    EvidenceKind.PRIMARY_EMPIRICAL: 0.92,
    EvidenceKind.REPLICATION: 0.96,
    EvidenceKind.SYSTEMATIC_REVIEW: 0.95,
    EvidenceKind.OFFICIAL_DATA: 0.90,
    EvidenceKind.PRIMARY_DOCUMENT: 0.86,
    EvidenceKind.DIRECT_OBSERVATION: 0.76,
    EvidenceKind.SECONDARY_ANALYSIS: 0.70,
    EvidenceKind.EXPERT_SUMMARY: 0.55,
    EvidenceKind.MODEL_OBSERVATION: 0.0,
    EvidenceKind.UNSOURCED: 0.0,
}


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
    provenance_verified: bool = False
    preregistered: bool = False
    data_available: bool = False
    code_available: bool = False
    sample_size: int | None = None
    uncertainty_reported: bool = False


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    minimum_independent_support: int = 2
    minimum_total_quality: float = 1.25
    minimum_mean_quality: float = 0.58
    require_empirical_support: bool = True
    require_reproducibility_signal: bool = True
    require_independent_replication_for_experiments: bool = True
    require_provenance_verified: bool = True
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
    provenance_verified_support: int
    total_quality: float
    mean_quality: float
    reproducibility_signal: bool
    independent_replication: bool
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


def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()


def _finite_score(value: float, *, name: str) -> float:
    number = float(value)
    if not math.isfinite(number): raise ValueError(f"{name} must be finite")
    if not 0.0 <= number <= 1.0: raise ValueError(f"{name} must be between 0 and 1")
    return number


def _age_days(stamp: str, now: datetime) -> float | None:
    if not stamp: return None
    try: when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError: return None
    if when.tzinfo is None: return None
    return max(0.0, (now - when.astimezone(UTC)).total_seconds() / 86400.0)


def _looks_falsifiable(claim: str) -> bool:
    text = " ".join(claim.split()).strip()
    if len(text) < 8: return False
    lowered = text.casefold()
    if any(token in lowered for token in ("everyone knows", "obviously", "undeniably", "always true", "cannot be tested", "beyond measurement", "because i feel", "must be true", "probably somehow")):
        return False
    measurable = re.search(r"\b(is|are|was|were|causes?|increases?|decreases?|predicts?|contains?|occurred|measured|equals?|greater|less|associated|correlat)\b", lowered)
    return bool(measurable or re.search(r"\d", lowered))


def _methodology_cap(item: EvidenceItem) -> float:
    """Compute maximum defensible quality from inspectable evidence properties."""
    ceiling = _KIND_CEILINGS[item.kind]
    if ceiling == 0.0: return 0.0
    if item.kind in {EvidenceKind.PRIMARY_EMPIRICAL, EvidenceKind.REPLICATION}:
        cap = 0.42
        cap += 0.10 if item.peer_reviewed else 0.0
        cap += 0.08 if item.preregistered else 0.0
        cap += 0.08 if item.data_available else 0.0
        cap += 0.06 if item.code_available else 0.0
        cap += 0.08 if item.uncertainty_reported else 0.0
        cap += 0.05 if item.sample_size is not None and item.sample_size > 0 else 0.0
        cap += 0.05 if item.primary else 0.0
        return min(ceiling, cap)
    if item.kind == EvidenceKind.SYSTEMATIC_REVIEW:
        cap = 0.62 + (0.10 if item.peer_reviewed else 0.0) + (0.08 if item.data_available else 0.0) + (0.06 if item.uncertainty_reported else 0.0)
        return min(ceiling, cap)
    if item.kind == EvidenceKind.OFFICIAL_DATA:
        return min(ceiling, 0.72 + (0.08 if item.data_available else 0.0) + (0.05 if item.uncertainty_reported else 0.0))
    if item.kind == EvidenceKind.PRIMARY_DOCUMENT:
        return min(ceiling, 0.74 if item.primary else 0.60)
    if item.kind == EvidenceKind.DIRECT_OBSERVATION:
        return min(ceiling, 0.58 + (0.08 if item.reproducible else 0.0))
    if item.kind == EvidenceKind.SECONDARY_ANALYSIS:
        return min(ceiling, 0.55 + (0.08 if item.peer_reviewed else 0.0))
    if item.kind == EvidenceKind.EXPERT_SUMMARY:
        return min(ceiling, 0.45 + (0.05 if item.peer_reviewed else 0.0))
    return 0.0


def effective_evidence_quality(item: EvidenceItem) -> float:
    requested = _finite_score(item.quality, name="evidence quality")
    return round(min(requested, _methodology_cap(item)), 6)


def _evidence_payload(item: EvidenceItem) -> dict[str, Any]:
    data = asdict(item); data["kind"] = item.kind.value; return data


class TruthVerifier:
    def __init__(self, policy: VerificationPolicy | None = None) -> None:
        self.policy = policy or VerificationPolicy()
        if self.policy.minimum_independent_support < 1: raise ValueError("minimum_independent_support must be >= 1")
        if self.policy.provisional_independent_support < 1: raise ValueError("provisional_independent_support must be >= 1")

    def verify_claim(self, claim: str, evidence: Iterable[EvidenceItem], *, falsifiable: bool | None = None, now: datetime | None = None) -> ClaimVerification:
        claim = " ".join(str(claim).split()).strip()
        if not claim: raise ValueError("claim cannot be blank")
        now = now or datetime.now(UTC)
        if now.tzinfo is None: raise ValueError("verification time must be timezone-aware")
        claim_falsifiable = _looks_falsifiable(claim) if falsifiable is None else bool(falsifiable)

        accepted: list[EvidenceItem] = []; rejected: list[EvidenceItem] = []; reasons: list[str] = []
        for raw in evidence:
            quality = effective_evidence_quality(raw)
            item = replace(raw, quality=quality)
            if not item.source_id.strip() or not item.independence_group.strip(): rejected.append(item); continue
            if item.kind in _NON_EVIDENCE_KINDS: rejected.append(item); continue
            if self.policy.require_provenance_verified and not item.provenance_verified: rejected.append(item); continue
            age = _age_days(item.observed_at, now)
            if self.policy.max_source_age_days is not None and age is not None and age > self.policy.max_source_age_days: rejected.append(item); continue
            accepted.append(item)

        support = [e for e in accepted if e.supports]; contradictions = [e for e in accepted if not e.supports]
        support_groups = {e.independence_group for e in support}; contradiction_groups = {e.independence_group for e in contradictions}
        empirical_support = sum(1 for e in support if e.kind in _EMPIRICAL_KINDS)
        provenance_verified_support = sum(1 for e in support if e.provenance_verified)
        total_quality = sum(e.quality for e in support); mean_quality = total_quality / len(support) if support else 0.0
        reproducible = any(e.reproducible or e.kind in {EvidenceKind.REPLICATION, EvidenceKind.SYSTEMATIC_REVIEW} for e in support)
        experimental = any(e.kind in _EXPERIMENTAL_KINDS for e in support)
        replication_groups = {e.independence_group for e in support if e.kind == EvidenceKind.REPLICATION}
        primary_groups = {e.independence_group for e in support if e.kind == EvidenceKind.PRIMARY_EMPIRICAL}
        independent_replication = bool(replication_groups and (not primary_groups or bool(replication_groups - primary_groups)))

        if self.policy.require_falsifiable_claim and not claim_falsifiable: reasons.append("claim_not_falsifiable")
        if self.policy.require_empirical_support and empirical_support == 0: reasons.append("no_empirical_support")
        if self.policy.require_provenance_verified and provenance_verified_support == 0: reasons.append("no_verified_provenance")
        if len(support_groups) < self.policy.minimum_independent_support: reasons.append("insufficient_independent_support")
        if total_quality < self.policy.minimum_total_quality: reasons.append("insufficient_total_evidence_quality")
        if mean_quality < self.policy.minimum_mean_quality: reasons.append("insufficient_mean_evidence_quality")
        if self.policy.require_reproducibility_signal and not reproducible: reasons.append("no_reproducibility_signal")
        if self.policy.require_independent_replication_for_experiments and experimental and not independent_replication:
            reasons.append("no_independent_replication")
        if contradiction_groups: reasons.append("contradictory_empirical_evidence")

        if contradictions and self.policy.contradiction_blocks:
            state = VerificationState.CONTRADICTED
        elif not support and not accepted:
            state = VerificationState.SPECULATION; reasons.append("speculation_is_not_evidence")
        elif not reasons:
            state = VerificationState.VERIFIED
        elif empirical_support >= 1 and len(support_groups) >= self.policy.provisional_independent_support and not contradiction_groups and claim_falsifiable:
            state = VerificationState.PROVISIONAL
        else:
            state = VerificationState.UNVERIFIED

        reasons_tuple = tuple(dict.fromkeys(reasons))
        payload = {"claim": claim, "state": state.value, "empirical_support": empirical_support,
            "independent_support": len(support_groups), "independent_contradictions": len(contradiction_groups),
            "provenance_verified_support": provenance_verified_support, "total_quality": round(total_quality, 6),
            "mean_quality": round(mean_quality, 6), "reproducibility_signal": reproducible,
            "independent_replication": independent_replication, "falsifiable": claim_falsifiable,
            "reasons": reasons_tuple, "accepted_evidence": tuple(_evidence_payload(e) for e in accepted),
            "rejected_evidence": tuple(_evidence_payload(e) for e in rejected)}
        return ClaimVerification(claim, state, empirical_support, len(support_groups), len(contradiction_groups),
            provenance_verified_support, round(total_quality, 6), round(mean_quality, 6), reproducible,
            independent_replication, claim_falsifiable, reasons_tuple, tuple(accepted), tuple(rejected), _digest(payload))

    def verify_many(self, claims: Iterable[str], evidence_by_claim: Mapping[str, Iterable[EvidenceItem]], *, falsifiability: Mapping[str, bool] | None = None) -> VerificationBatch:
        results = [self.verify_claim(claim, evidence_by_claim.get(claim, ()), falsifiable=(falsifiability or {}).get(claim)) for claim in claims]
        verified = tuple(x for x in results if x.state == VerificationState.VERIFIED)
        provisional = tuple(x for x in results if x.state == VerificationState.PROVISIONAL)
        speculation = tuple(x for x in results if x.state == VerificationState.SPECULATION)
        contradicted = tuple(x for x in results if x.state == VerificationState.CONTRADICTED)
        unverified = tuple(x for x in results if x.state == VerificationState.UNVERIFIED)
        payload = {"verified": [x.attestation_sha256 for x in verified], "provisional": [x.attestation_sha256 for x in provisional],
            "irrelevant_speculation": [x.attestation_sha256 for x in speculation], "contradicted": [x.attestation_sha256 for x in contradicted],
            "unverified": [x.attestation_sha256 for x in unverified]}
        return VerificationBatch(verified, provisional, speculation, contradicted, unverified, _digest(payload))

    @staticmethod
    def verified_projection(batch: VerificationBatch) -> tuple[str, ...]: return tuple(item.claim for item in batch.verified)

    @staticmethod
    def epistemic_projection(batch: VerificationBatch) -> dict[str, Any]:
        return {"verified": [x.claim for x in batch.verified], "provisional": [x.claim for x in batch.provisional],
            "contradicted": [x.claim for x in batch.contradicted], "unverified": [x.claim for x in batch.unverified],
            "irrelevant_speculation": [x.claim for x in batch.irrelevant_speculation], "attestation_sha256": batch.attestation_sha256}


def verify_claim_attestation(result: ClaimVerification) -> bool:
    payload = {"claim": result.claim, "state": result.state.value, "empirical_support": result.empirical_support,
        "independent_support": result.independent_support, "independent_contradictions": result.independent_contradictions,
        "provenance_verified_support": result.provenance_verified_support, "total_quality": result.total_quality,
        "mean_quality": result.mean_quality, "reproducibility_signal": result.reproducibility_signal,
        "independent_replication": result.independent_replication, "falsifiable": result.falsifiable,
        "reasons": result.reasons, "accepted_evidence": tuple(_evidence_payload(e) for e in result.accepted_evidence),
        "rejected_evidence": tuple(_evidence_payload(e) for e in result.rejected_evidence)}
    return _digest(payload) == result.attestation_sha256
