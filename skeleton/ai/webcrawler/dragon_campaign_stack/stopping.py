"""Conservative completion and stop decisions for Dragon research campaigns.

Capture completion, corroboration and reviewed knowledge are distinct outcomes.
Low novelty may justify stopping further acquisition but cannot certify claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .budget import BudgetProjection
from .contracts import CampaignMandate, digest, finite, integer
from .evidence import EvidenceInspection


@dataclass(frozen=True)
class ResearchStopGate:
    stop_acquisition: bool
    human_review_required: bool
    knowledge_verified: bool
    remaining_requests: int
    measured_novelty_count: int
    reasons: tuple[str, ...]
    next_actions: tuple[str, ...]
    decision_digest: str


def decide_campaign_stop(
    mandate: CampaignMandate,
    budget: BudgetProjection,
    evidence: EvidenceInspection, *,
    novelty_scores: Iterable[float],
    now: float,
    authorized: bool,
    plateau_window: int = 5,
    novelty_floor: float = 0.03,
) -> ResearchStopGate:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(budget, BudgetProjection) or not isinstance(evidence, EvidenceInspection):
        raise TypeError("validated campaign reports required")
    integer(plateau_window, "plateau window", 2, 128)
    finite(novelty_floor, "novelty floor", 0, 1)
    history = tuple(novelty_scores)
    if len(history) > 512:
        raise ValueError("novelty observation budget exceeded")
    for score in history:
        finite(score, "novelty observation", 0, 1)
    plateau = len(history) >= plateau_window and max(history[-plateau_window:]) <= novelty_floor
    reasons = []
    if budget.pending_dispatch:
        reasons.append("unknown_remote_outcome")
    if budget.exhausted:
        reasons.extend(budget.blockers)
    if not evidence.sources:
        reasons.append("no_retained_sources")
    if evidence.rejected_sources:
        reasons.append("source_integrity_rejections")
    if not evidence.passages:
        reasons.append("no_query_supported_passages")
    if any(x.risk_count for x in evidence.sources):
        reasons.append("untrusted_instruction_risks")
    if any(x.text_truncated for x in evidence.sources):
        reasons.append("partial_source_retention")
    if plateau:
        reasons.append("low_information_gain_plateau")
    # Never equate "multiple hosts" with independent source corroboration.
    # No unreviewed crawl has human-reviewed factual source verification.
    reasons.append("human_evidence_review_required")
    stop = (budget.exhausted or plateau or budget.pending_dispatch
            or budget.requests_remaining <= 0)
    if budget.pending_dispatch:
        actions = ("reconcile_remote_outcome_before_any_new_acquisition",)
    elif stop and budget.exhausted:
        actions = ("seek_new_explicit_budget_and_consent", "human_review_evidence")
    elif plateau:
        actions = ("reassess_queries_and_source_diversity", "human_review_evidence")
    elif not evidence.passages:
        actions = ("seek_relevant_sources_within_current_authority",)
    else:
        actions = ("continue_bounded_capture_if_desired", "submit_to_human_review")
    payload = {
        "mandate": mandate.fingerprint,
        "stop": stop, "reasons": sorted(set(reasons)),
        "actions": actions, "novelty": history,
        "floor": novelty_floor, "window": plateau_window,
        "remaining": budget.requests_remaining,
    }
    return ResearchStopGate(
        stop_acquisition=bool(stop), human_review_required=True,
        knowledge_verified=False,
        remaining_requests=budget.requests_remaining,
        measured_novelty_count=len(history),
        reasons=tuple(sorted(set(reasons))),
        next_actions=actions,
        decision_digest=digest(payload),
    )
