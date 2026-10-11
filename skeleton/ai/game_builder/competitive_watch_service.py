"""Adaptive competitive intelligence adapter and multi-enemy delivery portfolio.

Execute a scan after a trusted crawler/operator refreshes the canonical Wiki
sources and RightsLedger. The service rechecks exact live source revision and
rights, reconstructs the last journal baseline, detects rivals, issues measured
deliverable work, and commits one all-or-nothing watch event. It DOES NOT fetch
untrusted competitor content, execute arbitrary recommendations, or pretend
that scheduled reviews already ran.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import timedelta
from typing import Mapping

from .contracts import canonical_digest
from .competitive_title_radar import (
    PlannedOriginalTitle,CompetingTitle,RivalSourceLink,
    ThreatAssessment,ThreatRadarError,RadarStandard,
    inspect_competing_titles,_date,
)
from .competitive_delivery_gate import (
    CompetitiveDeliveryReport,DeliveryDemand,
    VerifiedQualitySample,OriginalIdentityReview,TrustedCompetitionJudge,
    SuperiorityStandard,compare_competitive_delivery,
)
from .competitive_watch_book import CompetitionWatchBook,WatchDelta
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import ClearedResearchPacket
from .rights import RightsLedger


@dataclass(frozen=True,slots=True)
class CompetitiveWorkOrder:
    original_id: str
    axis: str
    benchmark_ids: tuple[str,...]
    minimum_quality_floor_bp: int
    highest_priority: int
    source_report_digests: tuple[str,...]
    protected_original_pillars: tuple[str,...]
    requirements: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.original_competitive_work_order.v1",
            original_id=self.original_id,axis=self.axis,
            benchmark_ids=list(self.benchmark_ids),
            minimum_quality_floor_bp=self.minimum_quality_floor_bp,
            highest_priority=self.highest_priority,
            source_report_digests=list(self.source_report_digests),
            protected_original_pillars=list(self.protected_original_pillars),
            requirements=list(self.requirements),
            status="needs_original_design_work_and_independent_replay",
            no_competitor_asset_or_story_copy=True,
            no_automatic_release_authority=True,
            requires_human_authored_solution=True)


@dataclass(frozen=True,slots=True)
class CompetitionRun:
    original_id: str
    as_of: str
    assessments: tuple[ThreatAssessment,...]
    reports: tuple[CompetitiveDeliveryReport,...]
    work_orders: tuple[CompetitiveWorkOrder,...]
    watch_delta: WatchDelta

    def payload(self):
        return dict(
            schema="skeleton.game_builder.competitive_intel_run.v1",
            original_id=self.original_id,as_of=self.as_of,
            threats=[x.payload() for x in self.assessments],
            delivery_reports=[x.payload() for x in self.reports],
            work_orders=[x.payload() for x in self.work_orders],
            watch_delta=self.watch_delta.payload(),
            background_crawler_executed=False,
            only_reviewed_rights_cleared_sources_used=True,
            enemy_rivals_are_internal_benchmarks_only=True,
            identity_originality_veto_applies=True)


def _stored_threat(data):
    if not isinstance(data,dict) or data.get("schema")!="skeleton.game_builder.competitor_threat.v1":
        raise ThreatRadarError("unrecognized previously recorded competitor threat")
    fields=[
        "original_id","rival_id","as_of","signal_evidence_digest",
        "status","overlap_bp","overlap_capabilities","independent_groups",
        "active_source_ids","blockers","next_review_hours",
        "source_grounded","identity_pillars_untouched"]
    try:
        threat=ThreatAssessment(**{
            k:tuple(data[k]) if k in {"overlap_capabilities","active_source_ids","blockers"}
            else data[k] for k in fields})
    except (TypeError,KeyError,ValueError) as exc:
        raise ThreatRadarError("previous competitor threat is corrupt") from exc
    if threat.payload()!=data:
        raise ThreatRadarError("stored enemy designation carries unauthorized metadata")
    return threat


def _stored_report(data):
    if not isinstance(data,dict) or data.get("schema")!="skeleton.game_builder.competitive_delivery.v1":
        raise ThreatRadarError("unrecognized earlier work-ratchet receipt")
    try:
        orders=tuple(DeliveryDemand(**entry) for entry in data["demands"])
        report=CompetitiveDeliveryReport(
            data["original_id"],data["rival_id"],data["as_of"],
            data["watch_digest"],data["baseline_design_digest"],
            data["competitor_status"],tuple(data["quality_results"]),
            orders,tuple(data["identity_blockers"]),
            data["qualified_to_claim_superiority"])
    except (TypeError,KeyError,ValueError) as exc:
        raise ThreatRadarError("earlier competitor work report is malformed") from exc
    if report.payload()!=data:
        raise ThreatRadarError("previous competitor quality or originality report was forged")
    return report


def compile_original_delivery_work(
    planned: PlannedOriginalTitle,
    reports: tuple[CompetitiveDeliveryReport,...],
    *,authorized: bool,
)->tuple[CompetitiveWorkOrder,...]:
    if not authorized:
        raise PermissionError("original work portfolio needs operator permission")
    if (not isinstance(planned,PlannedOriginalTitle)
            or type(reports) is not tuple
            or any(not isinstance(r,CompetitiveDeliveryReport) or
                   r.original_id!=planned.title_id for r in reports)):
        raise ThreatRadarError("portfolio only accepts full same-title comparisons")
    buckets=defaultdict(list)
    for report in reports:
        for gap in report.demands:
            buckets[gap.axis].append((report,gap))
    result=[]
    for axis,entries in sorted(buckets.items()):
        demanding=max(gap.target_floor_bp for _,gap in entries)
        rivals=tuple(sorted({rep.rival_id for rep,_ in entries}))
        receipts=tuple(sorted({rep.digest for rep,_ in entries}))
        blocked=tuple(sorted({gap.blocked_reason for _,gap in entries
                             if gap.blocked_reason}))
        conditions=(
            f"Meet or exceed the verified {axis} target on independent original-game "
            "scenarios using the same platform, players and test protocol.",
            "Preserve every immutable title-specific originality pillar.",
            "Improve design, code, player experience and polish without reproducing rival IP.",
            "Retain all safety, accessibility, rights and platform hard gates.",
            "Do not report victory before every benchmark axis and originality audit pass.",
            *(("Resolve benchmark qualification blockers: "+", ".join(blocked),)
              if blocked else ()),
        )
        result.append(CompetitiveWorkOrder(
            planned.title_id,axis,rivals,demanding,
            max(gap.priority for _,gap in entries),
            receipts,planned.identity_pillars,tuple(conditions)))
    return tuple(sorted(result,key=lambda x:(-x.highest_priority,x.axis)))


def review_competitive_frontier(
    journal: CompetitionWatchBook,
    planned: PlannedOriginalTitle,
    competitors: tuple[CompetingTitle,...],
    links: tuple[RivalSourceLink,...],
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    wiki: ReviewedKnowledgeStore,
    rights: RightsLedger,
    *,
    as_of: str,
    measurements: Mapping[str,tuple[VerifiedQualitySample,...]]|None=None,
    identity: OriginalIdentityReview|None=None,
    trusted_identity_reviewer: TrustedCompetitionJudge|None=None,
    trusted_judges: tuple[TrustedCompetitionJudge,...]=(),
    radar_standard: RadarStandard=RadarStandard(),
    delivery_standard: SuperiorityStandard=SuperiorityStandard(),
    authorized: bool,
)->CompetitionRun:
    if not authorized:
        raise PermissionError("competitive frontier requires explicit authorized scan")
    if not isinstance(journal,CompetitionWatchBook):
        raise ThreatRadarError("canonical local append-only competitor journal required")
    _date(as_of)
    history=journal.history(planned.title_id,authorized=True)
    prev=history[-1][0] if history else None
    threats=tuple(_stored_threat(x) for x in prev["assessments"]) if prev else ()
    earlier={
        x.rival_id:x for x in (
            _stored_report(row) for row in prev["delivery_reports"]
        )
    } if prev else {}
    if measurements is None:
        measurements={}
    if (not isinstance(measurements,Mapping)
            or any(k not in {r.title_id for r in competitors}
                   or type(v) is not tuple for k,v in measurements.items())):
        raise ThreatRadarError("quality benchmark samples must be by known rival")
    current=inspect_competing_titles(
        planned,competitors,links,brief,packet,wiki,rights,
        as_of=as_of,prior=threats,standard=radar_standard,authorized=True)
    reports=[]
    for threat in current:
        if threat.status!="enemy":
            continue
        reports.append(compare_competitive_delivery(
            planned,threat,measurements.get(threat.rival_id,()),rights,
            as_of=as_of,authorized=True,identity=identity,
            trusted_identity_reviewer=trusted_identity_reviewer,
            trusted_judges=trusted_judges,standard=delivery_standard,
            preceding=earlier.get(threat.rival_id)))
    reports=tuple(reports)
    orders=compile_original_delivery_work(planned,reports,authorized=True)
    delta=journal.record(planned,current,reports,as_of=as_of,authorized=True)
    return CompetitionRun(planned.title_id,as_of,current,reports,orders,delta)


__all__=["CompetitiveWorkOrder","CompetitionRun",
         "compile_original_delivery_work","review_competitive_frontier"]
