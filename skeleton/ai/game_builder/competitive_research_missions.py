"""Bridge tri-council learning gaps into the *existing* Dragon research planner.

Runs the genuine Dragon research mission planner, not a spoof crawler
executor. Intensity expands from focused scrutiny to cross-domain genre
research, plus higher effort after a user rejects a complete PDF packet.
Allowed discovery APIs: Wikipedia, Crossref, OpenAlex and Europe PMC;
each HTTP transport must independently enforce RFC 9309/terms/egress limits.
Metadata is NEVER admitted as verified Wiki truth automatically.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError
from .competitive_tri_council import ThreeRoundBattlePlan
from .competitive_user_critique import CurrentProjectCritique
from ..webcrawler.dragon_research_missions import (
    ResearchInterest,MissionPolicy,ResearchMission,plan_research,
)

DOMAINS={
    "gameplay":"video game input controls NPC quests deterministic world game design",
    "graphics":"video game rendering readability performance accessible art direction",
    "sound":"video game audio spatial hearing accessibility interactive music",
    "storyline":"video game narrative branching choices world simulation player agency",
}
ROUND_TOPICS=(6,12,20)


@dataclass(frozen=True,slots=True)
class CrawlerMissionFrontier:
    target_round: int
    epoch: int
    critique_digest: str
    planned_queries: int
    topics: tuple[str,...]
    genuine_dragon_mission: ResearchMission
    network_work_performed: bool=False

    def payload(self):
        return dict(
            schema="skeleton.game_builder.dragon_tri_council_discovery.v1",
            target_round=self.target_round,epoch=self.epoch,
            critique_digest=self.critique_digest,
            planned_queries=self.planned_queries,
            topics=list(self.topics),
            native_mission_fingerprint=self.genuine_dragon_mission.fingerprint,
            network_work_performed=self.network_work_performed,
            next_step="authorized_lawful_source_discovery_then_human_wiki_rights_review",
            public_metadata_is_not_training_permission=True)


def prepare_three_round_crawler_mission(
    battle: ThreeRoundBattlePlan,
    critique: CurrentProjectCritique,*,authorized: bool,
    consent: bool,
)->CrawlerMissionFrontier:
    if not authorized or not consent:
        raise PermissionError("real Dragon research planning needs operator consent")
    if (not isinstance(battle,ThreeRoundBattlePlan)
            or not isinstance(critique,CurrentProjectCritique)
            or battle.critique_digest!=critique.digest
            or battle.original_id!=critique.original_id
            or battle.epoch>3
            or not 0<=len(battle.rounds)<=2):
        raise ThreatRadarError("next Dragon mission requires exact incomplete user-approved research epoch")
    next_round=len(battle.rounds)+1
    candidates=[]
    # Must not select only one attractive quality dimension at the expense
    # of graphics/sound/story: reserve at least one per domain each round.
    for domain in DOMAINS:
        choices=sorted((c for c in critique.criticisms if c.domain==domain),
                       key=lambda x:(-x.priority,x.facet))
        if not choices:
            raise ThreatRadarError("incomplete 102-facet user project research")
        candidates.append(choices[0])
    all_items=sorted(critique.criticisms,key=lambda x:(-x.priority,x.facet))
    for item in all_items:
        if item.facet not in {x.facet for x in candidates}:
            candidates.append(item)
    count=ROUND_TOPICS[next_round-1]
    chosen=candidates[:count]
    interests=[]
    for pos,item in enumerate(chosen):
        domain=DOMAINS[item.domain]
        topic=f"{domain} {item.facet.replace('_',' ')}"
        # Native planner uses bounded positive weights, no arbitrary percent
        # promotion of opinions to evidence.
        importance=round(max(0.30,1-0.02*pos),5)
        interests.append(ResearchInterest(topic,importance))
    mission=plan_research(
        critique.original_id,tuple(interests),authorized=True,
        geographic_consent=False,
        policy=MissionPolicy(max_interests=count,max_queries=count*4,
                             include_places=False))
    return CrawlerMissionFrontier(
        next_round,battle.epoch,critique.digest,len(mission.queries),
        tuple(x.topic for x in interests),mission,False)


__all__=["CrawlerMissionFrontier","prepare_three_round_crawler_mission"]
