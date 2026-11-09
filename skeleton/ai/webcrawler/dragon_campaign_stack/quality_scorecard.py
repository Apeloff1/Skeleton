"""Quantified research readiness without confusing evidence with truth.

A deterministic diagnostic score is useful for prioritizing an operator's
review queue; it is not a calibrated probability, a network benchmark or
release readiness. Hard authority holds are never diluted by aggregate
scores or averaged with unconfirmed assertions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .contracts import CampaignMandate, digest
from .context_envelope import ResearchContextEnvelope
from .coverage import CoverageReport
from .independence_audit import IndependenceAudit
from .integration import CampaignInspection
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class QualityDimension:
    name: str
    numerator: int
    denominator: int
    ratio: float
    grade: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResearchScorecard:
    mandate_digest: str
    source_snapshot_digest: str
    dimensions: tuple[QualityDimension, ...]
    alerts: tuple[str, ...]
    objective_count: int
    query_count: int
    gathered_reference_count: int
    unresolved_claim_count: int
    advisory_priority_score: float
    decision: str
    scorecard_digest: str
    verification_granted: bool = False
    release_granted: bool = False


def _dimension(name: str, numerator: int, denominator: int,
               limitations: tuple[str, ...] = ()) -> QualityDimension:
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ValueError("invalid measured dimension")
    fraction = round(numerator / denominator, 8) if denominator else 0.0
    grade = ("insufficient_sample" if denominator == 0 else
             "unmet" if numerator == 0 else
             "partial" if numerator < denominator else
             "observed_complete_not_verified")
    return QualityDimension(name, numerator, denominator, fraction, grade, limitations)


def measure_research_scorecard(
    mandate: CampaignMandate,
    inspection: CampaignInspection,
    coverage: CoverageReport,
    policies: SourcePolicyProjection,
    fusion: RetrievalFusion,
    context: ResearchContextEnvelope,
    independence: IndependenceAudit | None = None,
    *,
    now: float,
    authorized: bool,
) -> ResearchScorecard:
    mandate.admit(now=now, authorized=authorized)
    if any(x != mandate.fingerprint for x in (
        inspection.mandate_digest, coverage.mandate_digest,
        policies.mandate_digest, fusion.mandate_digest,
        context.mandate_digest,
    )):
        raise PermissionError("cross-mandate scorecard inputs")
    snapshot = inspection.snapshot_digest
    if any(x != snapshot for x in (
        policies.source_snapshot_digest, fusion.source_snapshot_digest,
        context.source_snapshot_digest,
    )):
        raise PermissionError("scorecard receipt snapshot mismatch")
    if context.retrieval_digest != fusion.fusion_digest:
        raise PermissionError("context retrieval identity mismatch")
    if independence is not None and (
        independence.mandate_digest != mandate.fingerprint
        or independence.source_snapshot_digest != snapshot
    ):
        raise PermissionError("foreign source-independence audit")
    rows = (
        _dimension("source_policy_review_scope",
                   len(policies.allowed_source_ids), policies.source_count,
                   ("policy permits review only",)),
        _dimension("current_evidence_reference_coverage",
                   context.reference_count,
                   max(context.reference_count, len(fusion.results)),
                   ("retrieval relevance is not fact verification",)),
        _dimension("objective_minimum_reviewable_passages",
                   sum(min(x.reviewable_passages, x.passage_target)
                       for x in coverage.objectives),
                   sum(x.passage_target for x in coverage.objectives),
                   ("independence and human review remain mandatory",)),
        _dimension("objective_attested_independent_groups",
                   sum(min(x.independent_groups_attested, x.group_target)
                       for x in coverage.objectives),
                   sum(x.group_target for x in coverage.objectives),
                   ("mirrors and derivations may overstate independence",)),
    )
    alerts = list(inspection.diagnostics.holds)
    if policies.excluded_source_ids:
        alerts.append("source_policy_exclusions")
    if not fusion.results:
        alerts.append("no_current_retrieved_evidence")
    if not coverage.objectives:
        alerts.append("missing_finite_research_goals")
    if coverage.unresolved_count:
        alerts.append("operator_objective_review_outstanding")
    if independence and (independence.findings or any(
            x.effective_support_groups_upper_bound < x.asserted_support_groups
            for x in independence.claims)):
        alerts.append("source_independence_counter_audit_failed")
    alerts.append("external_content_never_trusted_or_auto_published")
    # This is a work-prioritization signal, not a reliability probability.
    priority = round(
        sum((1 - x.ratio) for x in rows) / max(1, len(rows)), 8,
    )
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": snapshot,
        "dimensions": [asdict(x) for x in rows],
        "alerts": sorted(set(alerts)),
        "coverage": coverage.coverage_digest,
        "policy": policies.policy_digest,
        "retrieval": fusion.fusion_digest,
        "context": context.envelope_digest,
        "independence": independence.audit_digest if independence else None,
        "priority": priority,
    }
    return ResearchScorecard(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=snapshot,
        dimensions=rows,
        alerts=tuple(sorted(set(alerts))),
        objective_count=len(coverage.objectives),
        query_count=fusion.evaluated_queries,
        gathered_reference_count=context.reference_count,
        unresolved_claim_count=(
            sum(len(x.blockers) > 0 for x in independence.claims)
            if independence else 0
        ),
        advisory_priority_score=priority,
        decision="human_review_hold",
        scorecard_digest=digest(payload),
    )
