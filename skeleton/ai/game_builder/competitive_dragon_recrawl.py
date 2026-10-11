"""Dragon native recrawl planning for game competitor enemy benchmarks.

Uses the canonical Dragon mission scheduler and current Wiki citations.
This queues *eligible work*, NOT web requests. A separately authorized
Dragon executor must enforce robots/terms, DNS/IP/redirect, egress limits,
host fairness and licence rights and deposit a newly human-reviewed Wiki
revision before the radar consumes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .contracts import canonical_digest
from .competitive_title_radar import (
    ThreatAssessment,RivalSourceLink,ThreatRadarError,_id,_date,
)
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger

from ..webcrawler.dragon_mission_scheduler import (
    RecrawlSource,plan_adaptive_recrawls,
)


@dataclass(frozen=True,slots=True)
class ReviewedCrawlHistory:
    source_id: str
    last_changed_epoch: int
    estimated_volatility_bp: int
    unchanged_rechecks: int = 0

    def __post_init__(self):
        _id(self.source_id,"recrawl source ID")
        if (type(self.last_changed_epoch) is not int
                or self.last_changed_epoch<0
                or type(self.estimated_volatility_bp) is not int
                or not 0<=self.estimated_volatility_bp<=10000
                or type(self.unchanged_rechecks) is not int
                or not 0<=self.unchanged_rechecks<=100000):
            raise ThreatRadarError("bounded sourced historical volatility required")


@dataclass(frozen=True,slots=True)
class DragonRecrawlDemand:
    source_id: str
    competitor_id: str
    source_url: str
    source_revision_digest: str
    due: bool
    next_due_epoch: int
    urgency_bp: int
    priority: int
    source_evidence_digest: str

    def payload(self):
        return dict(
            schema="skeleton.game_builder.competitor_dragon_recrawl.v1",
            source_id=self.source_id,competitor_id=self.competitor_id,
            source_url=self.source_url,
            source_revision_digest=self.source_revision_digest,
            due=self.due,next_due_epoch=self.next_due_epoch,
            urgency_bp=self.urgency_bp,priority=self.priority,
            source_evidence_digest=self.source_evidence_digest,
            can_crawl_without_external_host_approval=False,
            is_verified_knowledge_revision_not_yet=False)


@dataclass(frozen=True,slots=True)
class DragonRecrawlQueue:
    owner: str
    evidence_root: str
    as_of: str
    orders: tuple[DragonRecrawlDemand,...]
    eligible_for_host_dispatch: tuple[str,...]
    dispatch_deferred_reasons: tuple[str,...]

    def payload(self):
        return dict(
            schema="skeleton.game_builder.dragon_competitive_monitor.v1",
            owner=self.owner,evidence_root=self.evidence_root,as_of=self.as_of,
            orders=[x.payload() for x in self.orders],
            eligible_for_host_dispatch=list(self.eligible_for_host_dispatch),
            dispatch_deferred_reasons=list(self.dispatch_deferred_reasons),
            read_only_dragon_scheduler_reused=True,
            independent_source_groups_never_duplicated=True,
            actual_network_fetches=0,
            actual_knowledge_promotions=0,
            actual_os_background_jobs_created=0)


def plan_dragon_competitor_recrawls(
    wiki: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    rights: RightsLedger,
    threats: tuple[ThreatAssessment,...],
    links: tuple[RivalSourceLink,...],
    histories: tuple[ReviewedCrawlHistory,...], *,
    as_of: str,
    authorized: bool,
    crawl_consent: bool,
    host_safe_to_work: bool,
    max_sources: int=64,
)->DragonRecrawlQueue:
    if not authorized:
        raise PermissionError("independent Dragon competitor recrawl needs operator authority")
    if (type(crawl_consent) is not bool or type(host_safe_to_work) is not bool
            or type(max_sources) is not int or not 1<=max_sources<=256
            or type(threats) is not tuple or not 1<=len(threats)<=128
            or any(not isinstance(x,ThreatAssessment) for x in threats)
            or type(links) is not tuple
            or any(not isinstance(x,RivalSourceLink) for x in links)
            or type(histories) is not tuple
            or any(not isinstance(x,ReviewedCrawlHistory) for x in histories)):
        raise ThreatRadarError("bounded consent, host resource and typed recrawl evidence required")
    now=_date(as_of).timestamp()
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (brief.scope!="design_reference"
            or packet.knowledge_root!=brief.knowledge_root
            or packet.research_brief_digest!=brief.to_payload()["brief_digest"]):
        raise ThreatRadarError("recrawl must bind one exact live Wiki+rights snapshot")
    threats_by_id={t.rival_id:t for t in threats}
    links_by_id={l.source_id:l for l in links}
    states={s.source_id:s for s in histories}
    if (len(threats_by_id)!=len(threats)
            or len(links_by_id)!=len(links)
            or len(states)!=len(histories)
            or set(states)!={x.source_id for x in brief.citations}
            or set(links_by_id)!=set(states)
            or any(link.rival_id not in threats_by_id for link in links)):
        raise ThreatRadarError("recrawl sources must exactly cover reviewed competitor evidence")
    unique={hit.source_id:hit for hit in brief.citations}
    items=[]
    for source_id in sorted(states):
        hit=unique[source_id]
        link=links_by_id[source_id]
        state=states[source_id]
        if link.revision_digest!=hit.revision_digest:
            raise ThreatRadarError("Dragon source revision changed since competitor review")
        if _date(hit.observed_at).timestamp()>now:
            raise ThreatRadarError("reviewed game source from future")
        last_fetch=int(_date(hit.observed_at).timestamp())
        if state.last_changed_epoch>last_fetch:
            raise ThreatRadarError("Dragon last-change record newer than reviewed acquisition")
        t=threats_by_id[link.rival_id]
        priority=1.0 if t.status=="enemy" else 0.65 if t.status=="watch" else 0.3
        items.append(RecrawlSource(
            source_id,hit.source_url,last_fetch,state.last_changed_epoch,
            state.estimated_volatility_bp/10000,priority,
            state.unchanged_rechecks))
    if len(items)>max_sources:
        raise ThreatRadarError("competitor source budget exceeded; paginate through host caller")
    due=plan_adaptive_recrawls(
        items,now=now,max_sources=max_sources,
        minimum_interval=3600,maximum_interval=30*86400)
    by_id={x.source_id:x for x in items}
    orders=[]
    for row in due:
        hit=unique[row.source_id]
        t=threats_by_id[links_by_id[row.source_id].rival_id]
        priority=(
            100 if t.status=="enemy" else 65 if t.status=="watch" else 30)
        priority=min(10000,priority*100+round(row.urgency*100))
        orders.append(DragonRecrawlDemand(
            row.source_id,t.rival_id,hit.source_url,hit.revision_digest,
            row.due,int(row.next_due),round(row.urgency*10000),priority,
            canonical_digest([brief.knowledge_root,packet.rights_ledger_digest,
                              hit.source_id,hit.revision_digest])))
    orders.sort(key=lambda x:(not x.due,-x.priority,x.source_id))
    deferred=[]
    if not crawl_consent:
        deferred.append("no_crawl_consent")
    if not host_safe_to_work:
        deferred.append("host_busy_or_thermal_limit")
    return DragonRecrawlQueue(
        brief.owner,canonical_digest([
            brief.knowledge_root,packet.rights_ledger_digest]),
        as_of,tuple(orders),
        tuple(x.source_id for x in orders if x.due and not deferred),
        tuple(deferred))


__all__=["ReviewedCrawlHistory","DragonRecrawlDemand","DragonRecrawlQueue",
         "plan_dragon_competitor_recrawls"]
