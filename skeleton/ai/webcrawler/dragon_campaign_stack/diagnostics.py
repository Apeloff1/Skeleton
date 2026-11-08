"""Cost, completeness and failure diagnostics derived from canonical crawl state.

No p95/p99 or real-device performance is synthesized from local counters.
Metrics are snapshots and are not independent storage or scheduler authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .budget import BudgetProjection
from .contracts import CampaignMandate, digest
from .evidence import EvidenceInspection


@dataclass(frozen=True)
class CampaignDiagnostics:
    observed_requests: int
    retained_documents: int
    uncertain_bytes: int
    request_utilization: float
    document_utilization: float
    byte_utilization: float
    source_rejection_count: int
    injection_flagged_sources: int
    truncated_sources: int
    reviewable_passages: int
    untrusted_passages: int
    remaining_execution_grant: bool
    holds: tuple[str, ...]
    diagnostic_digest: str
    measured_latency_p95_ms: float | None = None
    measured_latency_p99_ms: float | None = None


def _ratio(used: int, cap: int) -> float:
    if cap <= 0:
        raise ValueError("invalid immutable capacity")
    if used < 0 or used > cap:
        raise ValueError("counter violates grant")
    return round(used / cap, 8)


def measure_campaign_diagnostics(
    mandate: CampaignMandate,
    budget: BudgetProjection,
    evidence: EvidenceInspection,
    *, extra_holds: Iterable[str] = (),
) -> CampaignDiagnostics:
    if not isinstance(budget, BudgetProjection) or not isinstance(evidence, EvidenceInspection):
        raise TypeError("validated budget and evidence required")
    holds = list(budget.blockers)
    if evidence.rejected_sources:
        holds.append("retained_source_integrity_rejections")
    if any(x.risk_count for x in evidence.sources):
        holds.append("external_instruction_risks_require_review")
    if any(x.text_truncated for x in evidence.sources):
        holds.append("truncated_sources_not_full_text_verified")
    for entry in extra_holds:
        if not isinstance(entry, str) or not entry or len(entry) > 128:
            raise ValueError("invalid diagnostic hold")
        holds.append(entry)
    holds = sorted(set(holds))
    payload = {
        "mandate": mandate.fingerprint,
        "requests": budget.requests_used,
        "bytes": budget.bytes_measured,
        "reserved": budget.bytes_uncertain,
        "documents": budget.documents_used,
        "source_count": len(evidence.sources),
        "rejected": evidence.rejected_sources,
        "passage_count": len(evidence.passages),
        "holds": holds,
    }
    return CampaignDiagnostics(
        observed_requests=budget.requests_used,
        retained_documents=budget.documents_used,
        uncertain_bytes=budget.bytes_uncertain,
        request_utilization=_ratio(budget.requests_used, mandate.request.max_requests),
        document_utilization=_ratio(budget.documents_used, mandate.request.max_documents),
        byte_utilization=_ratio(
            budget.bytes_measured + budget.bytes_uncertain,
            mandate.request.max_total_bytes,
        ),
        source_rejection_count=len(evidence.rejected_sources),
        injection_flagged_sources=sum(x.risk_count > 0 for x in evidence.sources),
        truncated_sources=sum(x.text_truncated for x in evidence.sources),
        reviewable_passages=sum(x.eligible_for_review for x in evidence.passages),
        untrusted_passages=len(evidence.passages),
        remaining_execution_grant=not holds,
        holds=tuple(holds),
        diagnostic_digest=digest(payload),
    )
