"""Rights-reviewed competitor convergence monitor for ORIGINAL game titles.

"Enemy" is a local, adversarial *benchmark classification* for competing
products, not a claim of wrongdoing, hostile behavior or permission to copy.
Signals come from the canonical reviewed Wiki and rights-cleared research
packet. This module performs no scraping and cannot attest publisher claims
without independent source evidence. It is deliberately separate from the
two internal model rivals of DualRivalForge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections import defaultdict
from hashlib import sha256
import re

from .contracts import canonical_digest, QUALITY_AXES
from .reviewed_knowledge import ReviewedKnowledgeStore, KnowledgeBrief
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger, RightsState, UseKind

_ID=re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
AXES=frozenset(QUALITY_AXES)


class ThreatRadarError(ValueError):
    """Invalid, misleading, unreviewed or stale competitive signal."""


def _id(value, label="identifier"):
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise ThreatRadarError(f"{label} must be a safe stable identifier")
    return value


def _text(value,label,max_chars=160):
    if (not isinstance(value,str) or value!=value.strip()
            or not 1<=len(value)<=max_chars or any(ord(c)<32 for c in value)):
        raise ThreatRadarError(f"{label} must be bounded normalized text")
    return value


def _sha(value,label="digest"):
    if not isinstance(value,str) or not _SHA.fullmatch(value):
        raise ThreatRadarError(f"{label} must be SHA-256")
    return value


def _tags(values,label,min_items=1,max_items=48):
    if (type(values) is not tuple or not min_items<=len(values)<=max_items
            or tuple(sorted(set(values)))!=values):
        raise ThreatRadarError(f"{label} must be unique sorted bounded tuple")
    for v in values:
        _id(v,label)
    return values


def _date(value):
    if not isinstance(value,str) or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",value):
        raise ThreatRadarError("canonical UTC observation time required")
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ThreatRadarError("invalid observed time") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ")!=value:
        raise ThreatRadarError("noncanonical observed time")
    return parsed


@dataclass(frozen=True,slots=True)
class PlannedOriginalTitle:
    title_id: str
    display_name: str
    design_digest: str
    platforms: tuple[str,...]
    genres: tuple[str,...]
    audiences: tuple[str,...]
    capabilities: tuple[str,...]
    identity_pillars: tuple[str,...]
    originality_floor_bp: int = 8000

    def __post_init__(self):
        _id(self.title_id,"original title ID")
        _text(self.display_name,"original title name")
        _sha(self.design_digest,"frozen design manifest")
        for name in ("platforms","genres","audiences","capabilities"):
            _tags(getattr(self,name),name)
        _tags(self.identity_pillars,"identity_pillars",3,32)
        if (set(self.capabilities)&set(self.identity_pillars)
                or type(self.originality_floor_bp) is not int
                or not 8000<=self.originality_floor_bp<=10000):
            raise ThreatRadarError("original identity requires distinct immutable pillars")

    def payload(self):
        return dict(
            title_id=self.title_id,display_name=self.display_name,
            design_digest=self.design_digest,platforms=list(self.platforms),
            genres=list(self.genres),audiences=list(self.audiences),
            capabilities=list(self.capabilities),
            identity_pillars=list(self.identity_pillars),
            originality_floor_bp=self.originality_floor_bp)


@dataclass(frozen=True,slots=True)
class CompetingTitle:
    title_id: str
    display_name: str
    platforms: tuple[str,...]
    genres: tuple[str,...]
    audiences: tuple[str,...]

    def __post_init__(self):
        _id(self.title_id,"rival title ID")
        _text(self.display_name,"rival display name")
        for field in ("platforms","genres","audiences"):
            _tags(getattr(self,field),field)

    def payload(self):
        return dict(
            title_id=self.title_id,display_name=self.display_name,
            platforms=list(self.platforms),
            genres=list(self.genres),audiences=list(self.audiences))


@dataclass(frozen=True,slots=True)
class RivalSourceLink:
    """Operator-submitted title association; evidence comes from Wiki, not this row."""

    rival_id: str
    source_id: str
    revision_digest: str

    def __post_init__(self):
        _id(self.rival_id,"rival_id")
        _id(self.source_id,"source_id")
        _sha(self.revision_digest,"source revision")

    def payload(self):
        return dict(rival_id=self.rival_id,source_id=self.source_id,
                    revision_digest=self.revision_digest)


@dataclass(frozen=True,slots=True)
class RadarStandard:
    enemy_entry_bp: int = 6500
    enemy_exit_bp: int = 4800
    min_independent_groups: int = 2
    min_convergent_capabilities: int = 2
    max_signal_age_days: int = 180
    minimum_relevance_bp: int = 2000

    def __post_init__(self):
        if (any(type(getattr(self,n)) is not int for n in (
                "enemy_entry_bp","enemy_exit_bp","min_independent_groups",
                "min_convergent_capabilities","max_signal_age_days",
                "minimum_relevance_bp"))
                or not 5000<=self.enemy_entry_bp<=9500
                or not 0<=self.enemy_exit_bp<self.enemy_entry_bp
                or not 2<=self.min_independent_groups<=8
                or not 2<=self.min_convergent_capabilities<=16
                or not 1<=self.max_signal_age_days<=365
                or not 0<=self.minimum_relevance_bp<=self.enemy_exit_bp):
            raise ThreatRadarError("bounded monotonic enemy radar standard required")

    def payload(self):
        return dict(enemy_entry_bp=self.enemy_entry_bp,
                    enemy_exit_bp=self.enemy_exit_bp,
                    min_independent_groups=self.min_independent_groups,
                    min_convergent_capabilities=self.min_convergent_capabilities,
                    max_signal_age_days=self.max_signal_age_days,
                    minimum_relevance_bp=self.minimum_relevance_bp)


@dataclass(frozen=True,slots=True)
class ThreatAssessment:
    original_id: str
    rival_id: str
    as_of: str
    signal_evidence_digest: str
    status: str
    overlap_bp: int
    overlap_capabilities: tuple[str,...]
    independent_groups: int
    active_source_ids: tuple[str,...]
    blockers: tuple[str,...]
    next_review_hours: int
    source_grounded: bool
    identity_pillars_untouched: bool = True

    def payload(self):
        return dict(
            schema="skeleton.game_builder.competitor_threat.v1",
            original_id=self.original_id,rival_id=self.rival_id,
            as_of=self.as_of,signal_evidence_digest=self.signal_evidence_digest,
            status=self.status,overlap_bp=self.overlap_bp,
            overlap_capabilities=list(self.overlap_capabilities),
            independent_groups=self.independent_groups,
            active_source_ids=list(self.active_source_ids),
            blockers=list(self.blockers),
            next_review_hours=self.next_review_hours,
            source_grounded=self.source_grounded,
            identity_pillars_untouched=self.identity_pillars_untouched,
            enemy_is_internal_competitor_benchmark_only=True,
            accusation_or_hostility=False,
            permission_to_copy_competitor_assets=False)


def _overlap(left,right):
    return 10000*len(set(left)&set(right))//len(set(left)|set(right))


def inspect_competing_titles(
    planned: PlannedOriginalTitle,
    rivals: tuple[CompetingTitle,...],
    links: tuple[RivalSourceLink,...],
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    wiki: ReviewedKnowledgeStore,
    rights: RightsLedger,*,
    as_of: str,authorized: bool,
    standard: RadarStandard=RadarStandard(),
    prior: tuple[ThreatAssessment,...]=(),
)->tuple[ThreatAssessment,...]:
    """Assess fresh source-backed capability overlap with hysteretic enemy status.

    Relevance of common audiences/platforms is never sufficient on its own:
    two independent source groups must corroborate two *actual* overlapping
    mechanics. Retrieval is freshness checked against live canonical Wiki and
    rights records before any threat enters the radar.
    """
    if not authorized:
        raise PermissionError("competitive intelligence requires operator authority")
    if (not isinstance(planned,PlannedOriginalTitle)
            or type(rivals) is not tuple or not 1<=len(rivals)<=128
            or any(not isinstance(r,CompetingTitle) for r in rivals)
            or type(links) is not tuple or len(links)>1024
            or any(not isinstance(z,RivalSourceLink) for z in links)
            or not isinstance(standard,RadarStandard)
            or type(prior) is not tuple
            or any(not isinstance(x,ThreatAssessment) for x in prior)):
        raise ThreatRadarError("bounded typed original plans and inspected rivals required")
    stamp=_date(as_of)
    if (len({r.title_id for r in rivals})!=len(rivals)
            or planned.title_id in {r.title_id for r in rivals}):
        raise ThreatRadarError("rivals must be distinct external title identities")
    if (len({(l.rival_id,l.source_id) for l in links})!=len(links)
            or len({l.source_id for l in links})!=len(links)):
        raise ThreatRadarError("the same source cannot be assigned to multiple rivals")
    if not isinstance(brief,KnowledgeBrief) or not isinstance(packet,ClearedResearchPacket):
        raise ThreatRadarError("reviewed Wiki and exact rights clearance required")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (brief.owner!=packet.owner or brief.scope!="design_reference"
            or brief.to_payload()["brief_digest"]!=packet.research_brief_digest
            or brief.knowledge_root!=packet.knowledge_root
            or canonical_digest([x.to_payload() for x in brief.citations])!=
               canonical_digest([x.to_payload() for x in packet.citations])):
        raise ThreatRadarError("Wiki citations and legal clearance are not identical")
    allowed={r.title_id:r for r in rivals}
    if any(l.rival_id not in allowed for l in links):
        raise ThreatRadarError("source refers to unknown competitor")
    past={x.rival_id:x for x in prior}
    if (len(past)!=len(prior)
            or any(x.original_id!=planned.title_id or _date(x.as_of)>=stamp
                   for x in prior)
            or set(past)-set(allowed)):
        raise ThreatRadarError("stale, duplicate or different-title radar baseline")
    link_index={l.source_id:l for l in links}
    seen_by_rival=defaultdict(list)
    for citation in brief.citations:
        link=link_index.get(citation.source_id)
        if link is None:
            raise ThreatRadarError("every reviewed citation must have a mapped competitor")
        competitor=allowed[link.rival_id]
        if link.revision_digest!=citation.revision_digest:
            raise ThreatRadarError("competitor signal is linked to a stale source version")
        if competitor.display_name.casefold() not in citation.source_title.casefold():
            raise ThreatRadarError("reviewed source title does not identify claimed competitor")
        when=_date(citation.observed_at)
        if when>stamp:
            raise ThreatRadarError("competitor source observation is from future")
        record=rights.source(citation.source_id)
        if (record.rights_state in {RightsState.UNKNOWN_QUARANTINE,RightsState.FORBIDDEN}
                or UseKind.FACTS_IDEAS_REFERENCE not in record.allowed_uses):
            raise ThreatRadarError("competitive source references not permitted")
        if (stamp-when).days<=standard.max_signal_age_days:
            seen_by_rival[competitor.title_id].append(citation)
    if set(link_index)!={c.source_id for c in brief.citations}:
        raise ThreatRadarError("linked source without reviewed citation")
    result=[]
    for competitor in sorted(rivals,key=lambda r:r.title_id):
        latest=seen_by_rival[competitor.title_id]
        by_mechanic=defaultdict(set)
        active_ids=set()
        independent=set()
        for citation in latest:
            # Only explicit reviewed source assertions may contribute to
            # mechanic overlap; audience/genre are operator metadata only.
            if citation.stance!="supports" or citation.confidence_ppm<600000:
                continue
            active_ids.add(citation.source_id)
            independent.add(citation.dependence_group)
            if citation.mechanic in planned.capabilities:
                by_mechanic[citation.mechanic].add(citation.dependence_group)
        supported=tuple(sorted(
            mechanic for mechanic,groups in by_mechanic.items()
            if len(groups)>=standard.min_independent_groups))
        # Prevent unverified many-tags metadata from creating an enemy.
        mechanic_bp=10000*len(supported)//len(planned.capabilities)
        score=(65*mechanic_bp
               +15*_overlap(planned.audiences,competitor.audiences)
               +10*_overlap(planned.genres,competitor.genres)
               +10*_overlap(planned.platforms,competitor.platforms))//100
        blockers=[]
        if len(independent)<standard.min_independent_groups:
            blockers.append("insufficient_independent_reviewed_source_groups")
        if len(supported)<standard.min_convergent_capabilities:
            blockers.append("insufficient_corroborated_converging_mechanics")
        if len(latest)==0:
            blockers.append("stale_or_missing_competitor_research")
        previous=past.get(competitor.title_id)
        previously_enemy=previous is not None and previous.status=="enemy"
        if blockers:
            status="watch" if score>=standard.minimum_relevance_bp else "insufficient_evidence"
        elif score>=standard.enemy_entry_bp:
            status="enemy"
        elif previously_enemy and score>=standard.enemy_exit_bp:
            status="enemy"
        elif score>=standard.minimum_relevance_bp:
            status="watch"
        else:
            status="low_relevance"
        # This is a *recommended polling cadence*, not a claim of
        # already-running crawler tasks or guaranteed website availability.
        hours=(12 if status=="enemy" else 48 if status=="watch" else 168)
        result.append(ThreatAssessment(
            planned.title_id,competitor.title_id,as_of,
            canonical_digest(dict(
                knowledge_root=brief.knowledge_root,
                rights_root=packet.rights_ledger_digest,
                source_revisions=sorted(
                    [[x.source_id,x.revision_digest] for x in latest]),
                as_of=as_of)),
            status,score,supported,len(independent),
            tuple(sorted(active_ids)),tuple(sorted(blockers)),
            hours, bool(latest)))
    return tuple(result)


__all__=["PlannedOriginalTitle","CompetingTitle","RivalSourceLink",
         "RadarStandard","ThreatAssessment","ThreatRadarError",
         "inspect_competing_titles"]
