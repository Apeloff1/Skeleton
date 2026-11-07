"""Deficit-aware offline strategy selection over a canonical frontier.

This aligns operator-authored research gaps with already-admitted frontier
URLs. It cannot broaden the frontier, introduce new hosts, increase quotas,
infer independent evidence, or silently renew source consent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urlsplit

from .budget import BudgetProjection
from .contracts import CampaignMandate, digest
from .coverage import CoverageReport
from .frontier_graph import FrontierTopology
from .objectives import ObjectivePlan
from .planner import build_campaign_plan
from .contracts import ResearchCandidate, CampaignPlan


@dataclass(frozen=True)
class MissionCandidate:
    url: str
    host: str
    objective_ids: tuple[str, ...]
    deficit_score: float
    estimated_information_value: float
    estimated_cost_bytes: int
    priority: float
    scheduled: bool
    reason: str


@dataclass(frozen=True)
class MissionStrategy:
    mandate_digest: str
    coverage_digest: str
    frontier_digest: str
    candidates: tuple[MissionCandidate, ...]
    proposed_plan: CampaignPlan
    goals_without_frontier_matches: tuple[str, ...]
    needs_human_review: bool
    strategy_digest: str
    acquisition_authorized: bool = False


def prioritize_unmet_research(
    mandate: CampaignMandate,
    objectives: ObjectivePlan,
    coverage: CoverageReport,
    frontier: FrontierTopology,
    budget: BudgetProjection,
    *,
    now: float,
    authorized: bool,
) -> MissionStrategy:
    mandate.admit(now=now, authorized=authorized)
    if objectives.mandate_digest != mandate.fingerprint:
        raise PermissionError("objective plan not bound to campaign")
    if coverage.mandate_digest != mandate.fingerprint or (
        coverage.objective_plan_digest != objectives.plan_digest
    ):
        raise PermissionError("coverage is not current to objectives")
    if frontier.frontier_count > mandate.limits.max_candidates:
        raise ValueError("mission exceeds bounded frontier")
    if frontier.snapshot_digest is None:
        raise ValueError("frontier missing source identity")
    coverage_by_id = {c.objective_id: c for c in coverage.objectives}
    expected = {o.objective_id for o in objectives.objectives}
    if set(coverage_by_id) != expected:
        raise PermissionError("objective coverage changed under strategy")
    # This is a lexical URL-path affinity heuristic, not a factual
    # assessment or a reason to execute a background HTTP request.
    proposals = []
    claimed_goals = set()
    scored: list[MissionCandidate] = []
    for row in frontier.arcs:
        target = urlsplit(row.child_url)
        url_terms = set(
            target.path.replace("/", " ").replace("-", " ")
            .replace("_", " ").casefold().split()
        )
        matched = []
        gap = 0.0
        for objective in objectives.objectives:
            report = coverage_by_id[objective.objective_id]
            terms = set(objective.question.casefold().split())
            terms.update(objective.required_terms)
            similarity = len(terms & url_terms) / max(1, len(terms))
            if similarity > 0:
                matched.append(objective.objective_id)
                claimed_goals.add(objective.objective_id)
                gap += objective.priority * (1.0 - report.evidence_coverage_ratio) * similarity
        penalty = 1.0 / (1 + row.attempts + row.depth)
        estimated = round(min(1.0, 0.1 + gap) * penalty, 8)
        proposals.append(ResearchCandidate(
            url=row.child_url,
            relevance=min(1.0, estimated),
            information_gain=min(1.0, estimated * 0.8),
            quality=0.1,
            expected_bytes=mandate.request.max_response_bytes,
            reason="unverified_unmet_objective_path_affinity",
            parent_url=row.parent_url,
            depth=row.depth,
        ))
        scored.append(MissionCandidate(
            url=row.child_url, host=target.hostname or "",
            objective_ids=tuple(sorted(matched)),
            deficit_score=round(gap, 8),
            estimated_information_value=estimated,
            estimated_cost_bytes=mandate.request.max_response_bytes,
            priority=estimated,
            scheduled=False,
            reason="candidate_requires_canonical_runner",
        ))
    plan = build_campaign_plan(
        mandate, proposals, budget, now=now, authorized=authorized,
    )
    scheduled = {item.url for item in plan.dispatches}
    output = tuple(
        sorted(
            (MissionCandidate(
                **{
                    **asdict(row),
                    "scheduled": row.url in scheduled,
                    "reason": (
                        "advisory_dispatch_slot_reserved"
                        if row.url in scheduled else
                        "not_selected_under_current_budget"
                    ),
                }
            ) for row in scored),
            key=lambda x: (-x.priority, x.url),
        )
    )
    missing = tuple(
        sorted(
            objective.objective_id for objective in objectives.objectives
            if objective.objective_id not in claimed_goals
        )
    )
    payload = {
        "mandate": mandate.fingerprint,
        "objectives": objectives.plan_digest,
        "coverage": coverage.coverage_digest,
        "topology": frontier.topology_digest,
        "budget": asdict(budget),
        "plan": plan.plan_digest,
        "candidates": [asdict(x) for x in output],
        "unmatched": missing,
    }
    return MissionStrategy(
        mandate_digest=mandate.fingerprint,
        coverage_digest=coverage.coverage_digest,
        frontier_digest=frontier.topology_digest,
        candidates=output,
        proposed_plan=plan,
        goals_without_frontier_matches=missing,
        needs_human_review=True,
        strategy_digest=digest(payload),
    )
