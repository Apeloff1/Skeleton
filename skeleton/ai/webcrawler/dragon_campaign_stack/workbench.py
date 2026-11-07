"""End-to-end deterministic Dragon research workbench over one immutable snapshot.

This is an application-owned, bounded composition of existing canonical
crawler plus source-review modules. All mutable authority stays in Mongo;
all outputs are source-linked diagnostic receipts with human review holds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .claims import (
    ResearchClaim, ClaimCitation, IndependenceAttestation,
    ClaimReviewMatrix, assess_claim_matrix,
)
from .contracts import CampaignMandate, digest, ensure_snapshot_scope
from .contradictions import CitationDependency, DisagreementGraph, build_disagreement_graph
from .coverage import CoverageReport, measure_objective_coverage
from .frontier_graph import FrontierTopology, analyze_frontier_topology
from .integration import CampaignInspection, inspect_crawl_campaign
from .lineage import SourceLink
from .mission_strategy import MissionStrategy, prioritize_unmet_research
from .objectives import ObjectivePlan, ResearchObjective, compile_objectives
from .references import CitationReport, verify_current_citations
from .risk_register import CrawlRiskRegister, compile_crawl_risks
from .robots_audit import RobotsAudit, audit_robots_state
from .stopping import ResearchStopGate, decide_campaign_stop
from .review_packet import ReviewPacket, create_review_packet


@dataclass(frozen=True)
class DragonWorkbench:
    mandate_digest: str
    source_snapshot_digest: str
    run_id: str
    inspection: CampaignInspection
    objectives: ObjectivePlan
    citation_verification: CitationReport
    claim_matrix: ClaimReviewMatrix | None
    coverage: CoverageReport
    disagreements: DisagreementGraph | None
    topology: FrontierTopology
    robots: RobotsAudit
    risks: CrawlRiskRegister
    strategy: MissionStrategy
    stopping: ResearchStopGate
    review_packet: ReviewPacket
    workbench_digest: str
    public_knowledge_ready: bool = False
    training_eligible: bool = False
    auto_execution_authorized: bool = False


def compose_dragon_workbench(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    *,
    objectives: Iterable[ResearchObjective],
    now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
    claims: Iterable[ResearchClaim] = (),
    claim_citations: Iterable[ClaimCitation] = (),
    independence_attestations: Iterable[IndependenceAttestation] = (),
    citation_dependencies: Iterable[CitationDependency] = (),
    source_links: Iterable[SourceLink] = (),
    novelty_scores: Iterable[float] = (),
) -> DragonWorkbench:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    # Prevalidate whole snapshot. Every downstream stage only sees the exact
    # same source revision, and revocations are never implicitly resolved.
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    revoked = tuple(revoked_source_ids)
    objective_rows = tuple(objectives)
    claims_rows = tuple(claims)
    citations_rows = tuple(claim_citations)
    groups = tuple(independence_attestations)
    dependencies = tuple(citation_dependencies)
    links = tuple(source_links)
    history = tuple(novelty_scores)
    inspection = inspect_crawl_campaign(
        canonical, mandate, now=now, authorized=authorized,
        revoked_source_ids=revoked, links=links,
    )
    plan = compile_objectives(
        mandate, objective_rows, now=now, authorized=authorized,
    )
    verification = verify_current_citations(
        mandate, canonical, inspection.evidence.passages,
        revoked_source_ids=revoked, now=now, authorized=authorized,
    )
    if claims_rows or citations_rows or groups or dependencies:
        if not claims_rows:
            raise ValueError("claim citations require a bounded claim universe")
        allowed_objectives = {x.objective_id for x in plan.objectives}
        if any(claim.objective_id not in allowed_objectives for claim in claims_rows):
            raise PermissionError("claim refers to out-of-mandate objective")
        matrix = assess_claim_matrix(
            mandate, claims_rows, citations_rows,
            inspection.evidence.passages, verification,
            groups, now=now, authorized=authorized,
        )
        disagreements = build_disagreement_graph(
            matrix, dependencies=dependencies,
        )
    else:
        matrix = None
        disagreements = None
    coverage = measure_objective_coverage(
        mandate, plan, inspection.evidence, verification, matrix,
        now=now, authorized=authorized,
    )
    topology = analyze_frontier_topology(
        canonical, mandate, now=now, authorized=authorized,
    )
    robots = audit_robots_state(
        canonical, mandate, now=now, authorized=authorized,
    )
    risks = compile_crawl_risks(
        canonical, mandate, now=now, authorized=authorized,
    )
    strategy = prioritize_unmet_research(
        mandate, plan, coverage, topology, inspection.budget,
        now=now, authorized=authorized,
    )
    stopping = decide_campaign_stop(
        mandate, inspection.budget, inspection.evidence,
        novelty_scores=history, now=now, authorized=authorized,
    )
    packet = create_review_packet(
        mandate, inspection, now=now, authorized=authorized,
        objectives=plan, coverage=coverage, claims=matrix,
        risks=risks, stopping=stopping,
    )
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "inspection": inspection.inspection_digest,
        "objectives": plan.plan_digest,
        "verification": verification.report_digest,
        "claims": matrix.matrix_digest if matrix else None,
        "coverage": coverage.coverage_digest,
        "disagreements": disagreements.graph_digest if disagreements else None,
        "topology": topology.topology_digest,
        "robots": robots.audit_digest,
        "risks": risks.risk_digest,
        "strategy": strategy.strategy_digest,
        "stop": stopping.decision_digest,
        "review": packet.packet_digest,
    }
    return DragonWorkbench(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        run_id=canonical["run_id"],
        inspection=inspection, objectives=plan,
        citation_verification=verification, claim_matrix=matrix,
        coverage=coverage, disagreements=disagreements,
        topology=topology, robots=robots, risks=risks,
        strategy=strategy, stopping=stopping,
        review_packet=packet, workbench_digest=digest(payload),
    )
