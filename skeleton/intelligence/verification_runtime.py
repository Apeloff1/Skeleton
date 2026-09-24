"""Deterministic verification runtime for canonical claim/evidence bundles.

This layer performs structural grounding, citation-integrity, source
independence, freshness/scope, contradiction, and action-postcondition checks.
It intentionally does not call a model and does not choose the final
verified/qualified/abstain/repair/block disposition; semantic review and final
adjudication belong to the later verification stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.contracts.verification import (
    EvidenceKind,
    EvidenceRelation,
    PostconditionState,
    VerificationBundle,
    VerificationEvidence,
    VerificationLevel,
)
from skeleton.intelligence.verification_policy import VerificationRequirement


@dataclass(frozen=True, slots=True)
class VerificationAssessment:
    structural_ok: bool
    grounding_ok: bool
    citation_integrity_ok: bool
    independence_ok: bool
    freshness_ok: bool
    scope_ok: bool
    postcondition_ok: bool
    contradiction_present: bool
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    independent_origin_ids: tuple[str, ...]
    issue_codes: tuple[str, ...]

    @property
    def satisfied(self) -> bool:
        return (
            self.structural_ok
            and self.grounding_ok
            and self.citation_integrity_ok
            and self.independence_ok
            and self.freshness_ok
            and self.scope_ok
            and self.postcondition_ok
            and not self.contradiction_present
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "structural_ok": self.structural_ok,
            "grounding_ok": self.grounding_ok,
            "citation_integrity_ok": self.citation_integrity_ok,
            "independence_ok": self.independence_ok,
            "freshness_ok": self.freshness_ok,
            "scope_ok": self.scope_ok,
            "postcondition_ok": self.postcondition_ok,
            "contradiction_present": self.contradiction_present,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "independent_origin_ids": list(self.independent_origin_ids),
            "issue_codes": list(self.issue_codes),
            "satisfied": self.satisfied,
        }


def _utc(value: datetime | None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _citation_integrity(evidence: VerificationEvidence) -> bool:
    if evidence.kind is not EvidenceKind.CITATION:
        return True
    return bool(evidence.locator and evidence.provenance_refs)


def _scope_covers(bundle: VerificationBundle, evidence: VerificationEvidence) -> bool:
    claim = bundle.claim
    if claim.population_scope and not set(claim.population_scope).issubset(
        evidence.population_scope
    ):
        return False
    if claim.environment_scope and not set(claim.environment_scope).issubset(
        evidence.environment_scope
    ):
        return False

    if claim.valid_from is not None:
        if evidence.valid_from is None or evidence.valid_from > claim.valid_from:
            return False
    if claim.valid_until is not None:
        if evidence.valid_until is None or evidence.valid_until < claim.valid_until:
            return False
    return True


def _fresh(
    evidence: VerificationEvidence,
    *,
    now: datetime,
    max_evidence_age_seconds: float,
) -> bool:
    age = (now - evidence.observed_at).total_seconds()
    return 0 <= age <= max_evidence_age_seconds


def verify_bundle(
    bundle: VerificationBundle,
    requirement: VerificationRequirement,
    *,
    now: datetime | None = None,
    max_evidence_age_seconds: float = 86_400.0,
) -> VerificationAssessment:
    """Run deterministic verification checks over one immutable bundle."""

    if not isinstance(bundle, VerificationBundle):
        raise TypeError("bundle must be VerificationBundle")
    if not isinstance(requirement, VerificationRequirement):
        raise TypeError("requirement must be VerificationRequirement")
    if isinstance(max_evidence_age_seconds, bool):
        raise ValueError("max_evidence_age_seconds must be positive")
    try:
        max_age = float(max_evidence_age_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_evidence_age_seconds must be positive") from exc
    if max_age <= 0:
        raise ValueError("max_evidence_age_seconds must be positive")
    instant = _utc(now)

    claim_id = bundle.claim.claim_id
    support = tuple(
        item
        for item in bundle.evidence
        if item.relation is EvidenceRelation.SUPPORTS
        and claim_id in item.bound_claim_ids
    )
    contradictions = tuple(
        item
        for item in bundle.evidence
        if item.relation is EvidenceRelation.CONTRADICTS
        and claim_id in item.bound_claim_ids
    )

    issues: list[str] = []
    structural_ok = True

    needs_grounding = requirement.level is not VerificationLevel.STRUCTURAL
    grounding_ok = not needs_grounding or bool(support)
    if not grounding_ok:
        issues.append("supporting_evidence_missing")

    invalid_citations = tuple(
        item for item in support + contradictions if not _citation_integrity(item)
    )
    citation_integrity_ok = not invalid_citations
    if invalid_citations:
        issues.append("citation_integrity_failed")

    if requirement.require_scope_match:
        scoped_support = tuple(item for item in support if _scope_covers(bundle, item))
        scope_ok = bool(scoped_support) if support else False
        if not scope_ok:
            issues.append("claim_scope_not_covered")
    else:
        scoped_support = support
        scope_ok = True

    if requirement.require_fresh_evidence:
        fresh_support = tuple(
            item
            for item in scoped_support
            if _fresh(item, now=instant, max_evidence_age_seconds=max_age)
        )
        freshness_ok = bool(fresh_support) if scoped_support else False
        if not freshness_ok:
            issues.append("fresh_supporting_evidence_missing")
    else:
        fresh_support = scoped_support
        freshness_ok = True

    eligible_support = tuple(
        item for item in fresh_support if _citation_integrity(item)
    )
    independent_origins = tuple(
        sorted(
            {
                item.origin_id
                for item in eligible_support
                if item.independent_for(bundle.claim)
            }
        )
    )
    independence_ok = (
        len(independent_origins) >= requirement.min_independent_origins
    )
    if not independence_ok:
        issues.append("independent_evidence_insufficient")

    contradiction_present = bool(contradictions)
    if contradiction_present:
        issues.append("contradictory_evidence_present")

    postcondition_ok = True
    if requirement.require_postcondition:
        if bundle.claim.operation_id is None:
            postcondition_ok = False
            issues.append("claim_operation_missing")
        else:
            relevant = tuple(
                item
                for item in bundle.postconditions
                if item.operation_id == bundle.claim.operation_id
            )
            satisfied = tuple(
                item for item in relevant if item.state is PostconditionState.SATISFIED
            )
            evidenced = tuple(item for item in satisfied if item.evidence_ids)
            postcondition_ok = bool(evidenced)
            if not relevant:
                issues.append("postcondition_missing")
            elif any(item.state is PostconditionState.UNKNOWN for item in relevant):
                issues.append("postcondition_unknown")
            elif any(item.state is PostconditionState.FAILED for item in relevant):
                issues.append("postcondition_failed")
            elif any(item.state is PostconditionState.COMPENSATED for item in relevant):
                issues.append("postcondition_compensated")
            if satisfied and not evidenced:
                issues.append("postcondition_evidence_missing")

    return VerificationAssessment(
        structural_ok=structural_ok,
        grounding_ok=grounding_ok,
        citation_integrity_ok=citation_integrity_ok,
        independence_ok=independence_ok,
        freshness_ok=freshness_ok,
        scope_ok=scope_ok,
        postcondition_ok=postcondition_ok,
        contradiction_present=contradiction_present,
        supporting_evidence_ids=tuple(item.evidence_id for item in support),
        contradicting_evidence_ids=tuple(item.evidence_id for item in contradictions),
        independent_origin_ids=independent_origins,
        issue_codes=tuple(dict.fromkeys(issues)),
    )


__all__ = [
    "VerificationAssessment",
    "verify_bundle",
]
