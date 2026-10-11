"""Deep enemy and genre-ancestry mission adapter for the canonical rival radar.

Consumes a previously verified CompetitionRun and a second independently
rights-cleared deep-research brief. All enemies in the watch are accounted for;
missing generations or signed comparisons become explicit work, never
fabricated gameplay weaknesses or automatically applied changes.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

from .contracts import canonical_digest
from .competitive_title_radar import (
    PlannedOriginalTitle, CompetingTitle, RivalSourceLink, ThreatRadarError,
)
from .competitive_watch_service import CompetitionRun
from .competitive_deep_analysis import (
    ScriptedProbe, FacetMeasurement, FacetVerdict,
    compose_deep_probe_scripts, score_deep_scripts,
)
from .competitive_evolution_chain import (
    ComparableEraTitle,EvidenceLineageEdge,RivalEvolutionChain,
    build_rival_evolution_chain,
)
from .competitive_counterproposals import (
    OriginalCounterproposal,propose_original_outclassing,
)
from .competitive_delivery_gate import TrustedCompetitionJudge
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import ClearedResearchPacket
from .rights import RightsLedger


@dataclass(frozen=True,slots=True)
class EnemyDeepDossier:
    original_id: str
    enemy_id: str
    platform: str
    evolution: RivalEvolutionChain
    analysis_scripts: tuple[ScriptedProbe,...]
    facet_verdicts: tuple[FacetVerdict,...]
    counterproposals: tuple[OriginalCounterproposal,...]
    unresolved_research: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.deep_enemy_dossier.v1",
            original_id=self.original_id,enemy_id=self.enemy_id,
            platform=self.platform,
            evolution=self.evolution.payload(),
            analysis_scripts=[x.payload() for x in self.analysis_scripts],
            facet_verdicts=[x.payload() for x in self.facet_verdicts],
            counterproposals=[x.payload() for x in self.counterproposals],
            unresolved_research=list(self.unresolved_research),
            full_domain_script_coverage=True,
            weakspot_claims_require_signed_matched_replays=True,
            original_work_only=True,
            actual_game_changes_performed=0)


@dataclass(frozen=True,slots=True)
class DeepCompetitorPortfolio:
    original_id: str
    overview_digest: str
    enemy_dossiers: tuple[EnemyDeepDossier,...]
    pending_analyzes: tuple[str,...]

    def payload(self):
        return dict(
            schema="skeleton.game_builder.deep_competitor_portfolio.v1",
            original_id=self.original_id,
            overview_digest=self.overview_digest,
            enemy_dossiers=[d.payload() for d in self.enemy_dossiers],
            pending_analyzes=list(self.pending_analyzes),
            no_disguised_missing_enemy=True,
            no_automatic_release_or_game_asset_copy=True)


def examine_enemy_genre_portfolio(
    current: CompetitionRun,
    original: PlannedOriginalTitle,
    rivals: tuple[CompetingTitle,...],
    histories: tuple[ComparableEraTitle,...],
    lineage_edges: tuple[EvidenceLineageEdge,...],
    linked_sources: tuple[RivalSourceLink,...],
    deep_brief: KnowledgeBrief,
    deep_packet: ClearedResearchPacket,
    wiki: ReviewedKnowledgeStore,
    rights: RightsLedger,*,
    platform: str,
    measurements: Mapping[str,tuple[FacetMeasurement,...]]|None=None,
    industry_cohorts: Mapping[str,tuple[FacetMeasurement,...]]|None=None,
    judges: tuple[TrustedCompetitionJudge,...]=(),
    authorized: bool,
)->DeepCompetitorPortfolio:
    if not authorized:
        raise PermissionError("comprehensive rival dossier demands operator permission")
    if (not isinstance(current,CompetitionRun)
            or not isinstance(original,PlannedOriginalTitle)
            or current.original_id!=original.title_id
            or platform not in original.platforms
            or type(rivals) is not tuple
            or any(not isinstance(x,CompetingTitle) for x in rivals)
            or len({x.title_id for x in rivals})!=len(rivals)
            or type(histories) is not tuple
            or type(lineage_edges) is not tuple
            or type(linked_sources) is not tuple
            or not isinstance(deep_brief,KnowledgeBrief)
            or not isinstance(deep_packet,ClearedResearchPacket)
            or type(judges) is not tuple):
        raise ThreatRadarError("typed original title and prior canonical watch run required")
    measurements={} if measurements is None else measurements
    industry_cohorts={} if industry_cohorts is None else industry_cohorts
    enemy_ids={x.rival_id for x in current.assessments if x.status=="enemy"}
    supplied={x.title_id:x for x in rivals}
    if (enemy_ids-set(supplied) or
            set(measurements)-enemy_ids or set(industry_cohorts)-enemy_ids
            or any(type(x) is not tuple for x in
                   (*measurements.values(),*industry_cohorts.values()))):
        raise ThreatRadarError("all enemies require explicit separate known-title research")
    dossiers=[]
    for assessment in sorted(current.assessments,key=lambda x:x.rival_id):
        if assessment.status!="enemy":
            continue
        rival=supplied[assessment.rival_id]
        chain=build_rival_evolution_chain(
            rival,assessment,histories,lineage_edges,
            deep_brief,deep_packet,wiki,rights,authorized=True)
        # Deep probes include every axis and facet even when no study was
        # collected: incomplete research must NOT masquerade as superiority.
        scripts=compose_deep_probe_scripts(
            original,assessment,deep_brief,deep_packet,wiki,rights,
            linked_sources,platform=platform,authorized=True)
        verdicts=score_deep_scripts(
            scripts,rival.title_id,original.title_id,
            measurements.get(rival.title_id,()),
            judges,as_of=current.as_of,authorized=True,
            industry_baselines=industry_cohorts.get(rival.title_id,()))
        proposals=propose_original_outclassing(
            original,assessment,chain,scripts,verdicts,authorized=True)
        remaining=list(chain.unresolved_ancestry)
        for verdict in verdicts:
            if verdict.status=="insufficient_evidence":
                remaining.append("await_deep_signed_evidence:"+verdict.facet)
        dossiers.append(EnemyDeepDossier(
            original.title_id,rival.title_id,platform,chain,
            scripts,verdicts,proposals,tuple(sorted(set(remaining)))))
    return DeepCompetitorPortfolio(
        original.title_id,canonical_digest(current.payload()),
        tuple(dossiers),tuple(sorted(enemy_ids-{x.enemy_id for x in dossiers})))


__all__=["EnemyDeepDossier","DeepCompetitorPortfolio",
         "examine_enemy_genre_portfolio"]
