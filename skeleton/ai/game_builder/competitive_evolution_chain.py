"""Evidence-reviewed genre evolution, ancestry and peer-comparison graph.

A comparable older game is NOT presumed to be the causal ancestor of another.
Edges are either corroborated documented influence or a clearly labeled
genre-comparable precedent. Every enemy receives a full chain only if the
source catalog can prove it. Missing generations are first-class research work.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .contracts import canonical_digest
from .competitive_title_radar import (
    CompetingTitle,PlannedOriginalTitle,ThreatAssessment,RivalSourceLink,
    ThreatRadarError,_id,_tags,_sha,
)
from .competitive_deep_analysis import ALL_FACETS
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import ClearedResearchPacket, require_cleared_research_current
from .rights import RightsLedger


@dataclass(frozen=True,slots=True)
class ComparableEraTitle:
    title_id: str
    display_name: str
    release_year: int
    era: str
    platforms: tuple[str,...]
    genres: tuple[str,...]
    distinctive_mechanics: tuple[str,...]
    evidence_root: str

    def __post_init__(self):
        from .competitive_title_radar import _text
        _id(self.title_id,"historical game ID")
        _text(self.display_name,"historical game title")
        _id(self.era,"console and PC era")
        _tags(self.platforms,"platforms")
        _tags(self.genres,"genres")
        _tags(self.distinctive_mechanics,"distinctive mechanics")
        _sha(self.evidence_root,"catalog evidence root")
        if (type(self.release_year) is not int
                or not 1950<=self.release_year<=2200):
            raise ThreatRadarError("credible original/historical release year required")

    def payload(self):
        return dict(title_id=self.title_id,display_name=self.display_name,
                    release_year=self.release_year,era=self.era,
                    platforms=list(self.platforms),genres=list(self.genres),
                    distinctive_mechanics=list(self.distinctive_mechanics),
                    evidence_root=self.evidence_root)


@dataclass(frozen=True,slots=True)
class EvidenceLineageEdge:
    older_id: str
    newer_id: str
    relation: str
    source_ids: tuple[str,...]
    mechanic_changes: tuple[str,...]

    def __post_init__(self):
        _id(self.older_id,"predecessor")
        _id(self.newer_id,"successor")
        if self.older_id==self.newer_id:
            raise ThreatRadarError("self-ancestry forbidden")
        if self.relation not in {"documented_influence","genre_comparable"}:
            raise ThreatRadarError("only typed evidence-supported comparative ancestry")
        _tags(self.source_ids,"lineage source IDs",2,24)
        _tags(self.mechanic_changes,"influenced mechanics",1,32)
        if set(self.mechanic_changes)-set(ALL_FACETS):
            raise ThreatRadarError("lineage changes need typed game-analysis facets")

    def payload(self):
        return dict(older_id=self.older_id,newer_id=self.newer_id,
                    relation=self.relation,
                    source_ids=list(self.source_ids),
                    mechanic_changes=list(self.mechanic_changes))


@dataclass(frozen=True,slots=True)
class LineageStage:
    title_id: str
    release_year: int
    era: str
    ancestor_ids: tuple[str,...]
    successors: tuple[str,...]
    comparable_mechanics: tuple[str,...]
    direct_influence_proven: bool
    evidence_receipt: str

    def payload(self):
        return dict(title_id=self.title_id,release_year=self.release_year,
                    era=self.era,ancestor_ids=list(self.ancestor_ids),
                    successors=list(self.successors),
                    comparable_mechanics=list(self.comparable_mechanics),
                    direct_influence_proven=self.direct_influence_proven,
                    evidence_receipt=self.evidence_receipt)


@dataclass(frozen=True,slots=True)
class RivalEvolutionChain:
    enemy_id: str
    genre: tuple[str,...]
    complete_competitor_coverage: bool
    verified_generations: int
    stages: tuple[LineageStage,...]
    direct_influence_edges: tuple[str,...]
    genre_comparable_edges: tuple[str,...]
    unresolved_ancestry: tuple[str,...]
    source_root: str
    is_causal_ancestry_proof: bool = False

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.genre_rival_evolution.v1",
            enemy_id=self.enemy_id,genre=list(self.genre),
            complete_competitor_coverage=self.complete_competitor_coverage,
            verified_generations=self.verified_generations,
            stages=[x.payload() for x in self.stages],
            direct_influence_edges=list(self.direct_influence_edges),
            genre_comparable_edges=list(self.genre_comparable_edges),
            unresolved_ancestry=list(self.unresolved_ancestry),
            source_root=self.source_root,
            is_causal_ancestry_proof=self.is_causal_ancestry_proof,
            genealogy_claimed_only_for_documented_influence=True,
            comparable_older_games_are_not_automatically_ancestors=True,
            no_protected_competitor_assets_reused=True)


def build_rival_evolution_chain(
    rival: CompetingTitle,
    threat: ThreatAssessment,
    titles: tuple[ComparableEraTitle,...],
    edges: tuple[EvidenceLineageEdge,...],
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    wiki: ReviewedKnowledgeStore,
    rights: RightsLedger,*,
    authorized: bool,
    min_generations: int=3,
    min_independent_groups: int=2,
)->RivalEvolutionChain:
    if not authorized:
        raise PermissionError("evolutionary rival analysis requires operator authorization")
    if (not isinstance(rival,CompetingTitle)
            or not isinstance(threat,ThreatAssessment)
            or threat.rival_id!=rival.title_id or threat.status!="enemy"
            or type(titles) is not tuple or not 1<=len(titles)<=256
            or type(edges) is not tuple or len(edges)>1024
            or any(not isinstance(x,ComparableEraTitle) for x in titles)
            or any(not isinstance(x,EvidenceLineageEdge) for x in edges)
            or type(min_generations) is not int or not 2<=min_generations<=12
            or type(min_independent_groups) is not int or
            not 2<=min_independent_groups<=8):
        raise ThreatRadarError("bounded typed enemy era chain and independent sources required")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (brief.scope!="design_reference" or brief.owner!=packet.owner
            or brief.knowledge_root!=packet.knowledge_root
            or packet.research_brief_digest!=brief.to_payload()["brief_digest"]):
        raise ThreatRadarError("evolution chain must use fresh canonical reviewed evidence")
    by_id={t.title_id:t for t in titles}
    if len(by_id)!=len(titles) or rival.title_id not in by_id:
        raise ThreatRadarError("one unique historical identity per known competitor")
    enemy_node=by_id[rival.title_id]
    if (enemy_node.display_name!=rival.display_name
            or set(enemy_node.platforms)!=set(rival.platforms)
            or not set(enemy_node.genres)&set(rival.genres)):
        raise ThreatRadarError("claimed enemy lineage disagrees with current competitor title")
    groups=defaultdict(set)
    hits_by_source=defaultdict(list)
    for hit in brief.citations:
        hits_by_source[hit.source_id].append(hit)
    graph=defaultdict(list)
    reverse=defaultdict(list)
    proof={}
    for edge in edges:
        old=by_id.get(edge.older_id)
        new=by_id.get(edge.newer_id)
        if old is None or new is None:
            raise ThreatRadarError("lineage edge refers to nonexistent historical title")
        if old.release_year>=new.release_year:
            raise ThreatRadarError("lineage edges must be chronological and acyclic")
        if not set(old.genres)&set(new.genres)&set(rival.genres):
            raise ThreatRadarError("unrelated genre crossovers require independent design review")
        if not (set(edge.mechanic_changes)&set(old.distinctive_mechanics)&
                set(new.distinctive_mechanics)):
            raise ThreatRadarError("reported evolution must compare shared, reviewed mechanics")
        evidence=[]
        for source_id in edge.source_ids:
            matching=[
                hit for hit in hits_by_source[source_id]
                if (hit.confidence_ppm>=650000
                    and hit.stance=="supports"
                    and ((edge.relation=="documented_influence" and
                          hit.mechanic=="lineage_influence") or
                         (edge.relation=="genre_comparable" and
                          hit.mechanic=="lineage_comparable"))
                    and old.display_name.casefold() in hit.source_title.casefold()
                    and new.display_name.casefold() in hit.source_title.casefold())
            ]
            if not matching:
                raise ThreatRadarError("lineage citation lacks reviewed relationship with both titles")
            evidence+=matching
        independent={hit.dependence_group for hit in evidence}
        if len(independent)<min_independent_groups:
            raise ThreatRadarError("no independent corroboration of claimed genre lineage")
        identity=(edge.older_id,edge.newer_id)
        if identity in proof:
            raise ThreatRadarError("duplicate versioned lineage link")
        proof[identity]=canonical_digest([
            edge.payload(),[[hit.source_id,hit.revision_digest,hit.note_id]
                            for hit in sorted(evidence,key=lambda h:(h.source_id,h.note_id))]])
        graph[edge.older_id].append(edge.newer_id)
        reverse[edge.newer_id].append(edge.older_id)
    # Restrict to proven paths terminating in this rival. Disconnected
    # genre titles are not materialized as ancestors by association.
    ancestors={rival.title_id}
    agenda=[rival.title_id]
    while agenda:
        for older in reverse[agenda.pop()]:
            if older not in ancestors:
                ancestors.add(older)
                agenda.append(older)
    if len(ancestors)<len(titles):
        # Unknown comparables are *not* evidence of this rival's ancestry.
        disconnected=tuple(sorted(set(by_id)-ancestors))
    else:
        disconnected=()
    depth={}
    for entry in sorted(ancestors,key=lambda i:(by_id[i].release_year,i)):
        depth[entry]=1+max((depth[a] for a in reverse[entry]),default=0)
    generations=depth[rival.title_id]
    incomplete=[]
    if generations<min_generations:
        incomplete.append("insufficient_verified_independent_generations")
    if disconnected:
        incomplete.append("unconnected_comparable_titles_excluded")
    if not reverse[rival.title_id]:
        incomplete.append("no_confirmed_rival_predecessor")
    stages=[]
    for title_id in sorted(ancestors,key=lambda x:(by_id[x].release_year,x)):
        title=by_id[title_id]
        connected=[(a,b) for a,b in proof
                   if (a==title_id or b==title_id) and
                   a in ancestors and b in ancestors]
        incoming=[e for e in edges if e.newer_id==title_id]
        stages.append(LineageStage(
            title_id,title.release_year,title.era,
            tuple(sorted(reverse[title_id])),
            tuple(sorted(b for b in graph[title_id] if b in ancestors)),
            title.distinctive_mechanics,
            bool(incoming) and all(e.relation=="documented_influence"
                                   for e in incoming),
            canonical_digest([title.payload(),[proof[x] for x in sorted(connected)]])))
    direct=tuple(sorted(
        proof[(e.older_id,e.newer_id)] for e in edges
        if e.relation=="documented_influence"
        and e.newer_id in ancestors))
    similar=tuple(sorted(
        proof[(e.older_id,e.newer_id)] for e in edges
        if e.relation=="genre_comparable"
        and e.newer_id in ancestors))
    return RivalEvolutionChain(
        rival.title_id,rival.genres,not incomplete,generations,
        tuple(stages),direct,similar,tuple(incomplete),
        canonical_digest([brief.knowledge_root,packet.rights_ledger_digest]),
        bool(direct) and not similar and not incomplete)


__all__=["ComparableEraTitle","EvidenceLineageEdge",
         "LineageStage","RivalEvolutionChain",
         "build_rival_evolution_chain"]
