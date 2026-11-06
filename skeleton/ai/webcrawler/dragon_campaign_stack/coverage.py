"""Mission objective coverage with unmet-goal next-action prioritization.

Coverage is a triage measurement of bound passage evidence, not a
declaration that a proposition has been verified or a source is independent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .claims import ClaimReviewMatrix
from .contracts import CampaignMandate, digest
from .evidence import EvidenceInspection
from .objectives import ObjectivePlan, ResearchObjective, objective_matches
from .references import CitationReport


@dataclass(frozen=True)
class ObjectiveCoverage:
    objective_id: str
    reviewable_passages: int
    independent_groups_attested: int
    passage_target: int
    group_target: int
    evidence_coverage_ratio: float
    unresolved_claim_count: int
    blocked: bool
    reasons: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class CoverageReport:
    mandate_digest: str
    objective_plan_digest: str
    objectives: tuple[ObjectiveCoverage, ...]
    unresolved_count: int
    total_candidate_evidence: int
    coverage_digest: str
    knowledge_verified: bool = False


def measure_objective_coverage(
    mandate: CampaignMandate,
    plan: ObjectivePlan,
    evidence: EvidenceInspection,
    verification: CitationReport,
    claims: ClaimReviewMatrix | None = None,
    *,
    now: float,
    authorized: bool,
) -> CoverageReport:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(plan, ObjectivePlan) or plan.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign objective plan")
    if not isinstance(evidence, EvidenceInspection) or not isinstance(verification, CitationReport):
        raise TypeError("verified source and inspection receipts required")
    if claims is not None and (
        not isinstance(claims, ClaimReviewMatrix)
        or claims.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("foreign claim matrix")
    checks = {(x.source_id, x.passage_hash): x for x in verification.entries}
    if len(checks) != len(verification.entries):
        raise ValueError("duplicate current-source check")
    all_keys = {(x.source_id, x.passage_hash) for x in evidence.passages}
    if all_keys != set(checks):
        raise PermissionError("source verification does not match evidence universe")
    observed = []
    for objective in plan.objectives:
        count = sum(
            objective_matches(objective, passage.text)
            and passage.eligible_for_review
            and checks[(passage.source_id, passage.passage_hash)].valid_for_review
            for passage in evidence.passages
        )
        matching = (
            [x for x in claims.claims if x.objective_id == objective.objective_id]
            if claims else []
        )
        groups = max(
            (x.attested_support_groups for x in matching), default=0
        )
        unresolved = sum(
            x.review_state != "source_review_pending" or x.unconfirmed_citations > 0
            for x in matching
        )
        reasons = []
        if count < objective.minimum_reviewable_passages:
            reasons.append("missing_anchored_passages")
        if groups < objective.minimum_attested_groups:
            reasons.append("missing_attested_source_independence")
        if unresolved:
            reasons.append("conflicting_or_unreviewed_claims")
        # The result is always a pre-human-review workflow step.
        reasons.append("human_claim_review_required")
        score = min(
            1.0, count / objective.minimum_reviewable_passages,
            groups / objective.minimum_attested_groups,
        )
        if count < objective.minimum_reviewable_passages:
            next_action = "collect_more_current_query_matching_evidence"
        elif groups < objective.minimum_attested_groups:
            next_action = "obtain_and_review_independent_source_provenance"
        elif unresolved:
            next_action = "resolve_source_contradictions_with_human_review"
        else:
            next_action = "submit_research_claims_for_human_review"
        observed.append(ObjectiveCoverage(
            objective_id=objective.objective_id,
            reviewable_passages=count,
            independent_groups_attested=groups,
            passage_target=objective.minimum_reviewable_passages,
            group_target=objective.minimum_attested_groups,
            evidence_coverage_ratio=round(score, 8),
            unresolved_claim_count=unresolved,
            blocked=True,
            reasons=tuple(reasons), next_action=next_action,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "plan": plan.plan_digest,
        "evidence": evidence.evidence_digest,
        "verification": verification.report_digest,
        "matrix": claims.matrix_digest if claims else None,
        "coverage": [asdict(x) for x in observed],
    }
    return CoverageReport(
        mandate_digest=mandate.fingerprint,
        objective_plan_digest=plan.plan_digest,
        objectives=tuple(observed),
        unresolved_count=sum(bool(x.reasons) for x in observed),
        total_candidate_evidence=len(evidence.passages),
        coverage_digest=digest(payload),
    )
