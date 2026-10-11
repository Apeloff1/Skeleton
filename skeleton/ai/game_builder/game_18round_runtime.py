"""Executable stage bridges from current Wiki/Dragon/reviewer actions to R3..18.

Not every one of sixteen stages can be truthfully 'completed' from a
function call: real gameplay recording, crawling, user approval and neural
inference require external, independently verified operations. These
bridges execute the stages for which typed evidence really exists, then
sign the output hash and advance the exact round journal. No fabricated
crawl or weight promotion is returned by an unavailable host integration.
"""
from __future__ import annotations
from dataclasses import dataclass

from .contracts import canonical_digest
from .game_18round_relevance import (
    RelevantKnowledge,SignedUtilityObservation,TopicPriority,score_task_knowledge,
)
from .game_18round_evolution import (
    EvolutionRun,EvolutionRoundReceipt,sign_round_receipt,accept_round,
    CrawlerDestination,CrawlerLogObservation,qualify_crawler_log_handoff,
    next_dragon_adjacency_mission,
)
from .game_18round_shadow_sandbox import (
    prepare_shadow_tickets,ModularShadowTicket,
)
from .game_training_flow import FlowPlan
from .game_post_weight_forensics import PostWeightReport
from .game_post_weight_dragon import plan_post_weight_dragon_research
from .game_dragon_peer_wisdom import (
    DragonWisdomAlmanac,SourceMediaReceipt,distill_dragon_peer_wisdom,
)
from .competitive_evolution_chain import RivalEvolutionChain
from .competitive_delivery_gate import TrustedCompetitionJudge
from .competitive_title_radar import ThreatRadarError,_date,_sha
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger,UseKind,RightsState


def _advance(
    state:EvolutionRun,round_no:int,status:str,
    report_digest:str,roots:tuple[str,...],
    reviewer:TrustedCompetitionJudge,as_of:str,*,
    authorized:bool,
    **gates,
)->EvolutionRun:
    if len(state.rounds)+3!=round_no:
        raise ThreatRadarError("live stage bridge may only execute the expected exact round")
    _date(as_of);_sha(report_digest)
    receipt=EvolutionRoundReceipt(
        round_no,(
            "relevance_predecessor_ultraweight",
            "shadow_preapproval_and_sandbox",
            "idle_priority_queue",
            "background_general_game_knowledge",
            "era_genre_theme_shadow",
            "objective_game_creation_standards",
            "project_target_crawler_research",
            "crawler_target_brief",
            "acquire_crawler_destinations",
            "crawler_logs_to_shadow_scrutiny",
            "adversarial_shadow_review",
            "weight_structure_optimization",
            "hyperweight_structuring",
            "probability_ordered_queue",
            "acquisition_and_gain_report",
            "adjacent_topic_recrawl")[round_no-3],
        state.task.task_digest,
        state.task.task_digest if not state.rounds else state.rounds[-1].digest,
        report_digest,tuple(sorted(set(roots))),status,True,
        reviewer.judge_id,as_of,"0"*64)
    return accept_round(state,sign_round_receipt(receipt,reviewer),
                        reviewer,authorized=authorized,**gates)


def execute_round3_relevance(
    state:EvolutionRun,
    library:ReviewedKnowledgeStore,brief:KnowledgeBrief,
    packet:ClearedResearchPacket,rights:RightsLedger,
    media:tuple[SourceMediaReceipt,...],
    topics:tuple[RelevantKnowledge,...],
    observed_outcomes:tuple[SignedUtilityObservation,...],
    outcome_signers:tuple[TrustedCompetitionJudge,...],
    historical_competitors:RivalEvolutionChain|None,*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
)->tuple[EvolutionRun,tuple[TopicPriority,...]]:
    if not authorized:raise PermissionError("current project knowledge priority needs permission")
    almanac=distill_dragon_peer_wisdom(
        library,brief,packet,rights,media,authorized=True)
    if almanac.project_id!=state.task.original_id:
        raise ThreatRadarError("reviewed almanac from another user's game")
    results=score_task_knowledge(
        state.task,almanac,topics,observed_outcomes,outcome_signers,
        lineage=historical_competitors,authorized=True)
    root=canonical_digest([row.payload() for row in results])
    return _advance(
        state,3,"research_recorded",root,
        (almanac.digest,packet.to_payload()["packet_digest"]),
        reviewer,as_of,authorized=True),results


def execute_round4_shadow_backlog(
    state:EvolutionRun,
    priorities:tuple[TopicPriority,...],
    original_games:FlowPlan,
    code_review_digest:str,
    allotted_mb:int,*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
)->tuple[EvolutionRun,tuple[ModularShadowTicket,...]]:
    if not authorized:raise PermissionError("shadow queue needs original game owner")
    if (not state.rounds or state.rounds[-1].round_number!=3
            or state.rounds[-1].report_digest!=canonical_digest(
                [p.payload() for p in priorities])):
        raise ThreatRadarError("shadow stage must match exact signed R3 task relevance")
    queue=prepare_shadow_tickets(
        state.task,priorities,original_games,
        original_code_review_digest=code_review_digest,
        allocated_memory_mb=allotted_mb,authorized=True)
    digest=canonical_digest([x.payload() for x in queue])
    return _advance(
        state,4,"shadow_queued",digest,
        (state.rounds[-1].report_digest,
         canonical_digest(original_games.payload()),
         code_review_digest),
        reviewer,as_of,authorized=True),queue


def execute_round9_project_research(
    state:EvolutionRun,
    current_post_weight:PostWeightReport,
    almanac:DragonWisdomAlmanac,*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
    consent:bool,
):
    if not authorized or not consent:
        raise PermissionError("task-directed Dragon recrawl needs explicit consent")
    mission=plan_post_weight_dragon_research(
        current_post_weight,almanac,authorized=True,consent=True)
    return _advance(
        state,9,"research_recorded",canonical_digest(mission.payload()),
        (current_post_weight.digest,almanac.digest),
        reviewer,as_of,authorized=True),mission


def derive_round11_reviewed_destinations(
    wiki:ReviewedKnowledgeStore,
    brief:KnowledgeBrief,
    packet:ClearedResearchPacket,
    rights:RightsLedger,*,
    authorized:bool,
)->tuple[CrawlerDestination,...]:
    if not authorized:raise PermissionError("current reviewed source destinations need authority")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (packet.knowledge_root!=brief.knowledge_root or
            packet.research_brief_digest!=brief.to_payload()["brief_digest"]):
        raise ThreatRadarError("real crawler destination sources must match canonical current Wiki")
    unique={}
    for cited in brief.citations:
        if cited.source_id in unique:
            if unique[cited.source_id].source_revision_digest!=cited.revision_digest:
                raise ThreatRadarError("source changed revision inside one reviewed research brief")
            continue
        rights_record=rights.source(cited.source_id)
        if (rights_record.rights_state in {
                RightsState.UNKNOWN_QUARANTINE,RightsState.FORBIDDEN}
                or UseKind.FACTS_IDEAS_REFERENCE not in rights_record.allowed_uses):
            raise ThreatRadarError("crawler destination with missing or revoked research rights")
        can_train=(UseKind.MODEL_TRAINING in rights_record.allowed_uses
                   and rights_record.rights_state not in {
                       RightsState.FACTS_IDEAS_REFERENCE_ONLY,
                       RightsState.RESTRICTED_REFERENCE_ONLY})
        root=canonical_digest({
            "source_id":cited.source_id,
            "url":cited.source_url,
            "revision":cited.revision_digest,
            "rights":rights_record.rights_binding_digest,
            "brief":packet.research_brief_digest})
        unique[cited.source_id]=CrawlerDestination(
            cited.source_id,cited.source_url,cited.revision_digest,
            rights_record.rights_binding_digest,root,
            "explicit_model_train" if can_train else "facts_ideas_reference")
    if not unique:raise ThreatRadarError("research brief has no original source destinations")
    return tuple(unique[s] for s in sorted(unique))


def execute_round11_destinations(
    state:EvolutionRun,
    wiki:ReviewedKnowledgeStore,
    brief:KnowledgeBrief,
    packet:ClearedResearchPacket,
    rights:RightsLedger,*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
)->tuple[EvolutionRun,tuple[CrawlerDestination,...]]:
    if not authorized:raise PermissionError("research destination lookup needs permission")
    sources=derive_round11_reviewed_destinations(
        wiki,brief,packet,rights,authorized=True)
    return _advance(
        state,11,"research_recorded",
        canonical_digest([x.payload() for x in sources]),
        (packet.to_payload()["packet_digest"],brief.knowledge_root),
        reviewer,as_of,authorized=True),sources


def execute_round12_crawler_log_ingestion(
    state:EvolutionRun,
    destinations:tuple[CrawlerDestination,...],
    reviewed_logs:tuple[CrawlerLogObservation,...],
    log_reviewers:tuple[TrustedCompetitionJudge,...],*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
)->tuple[EvolutionRun,dict]:
    if not authorized:raise PermissionError("safe source evidence must be reviewed")
    if (not state.rounds or state.rounds[-1].round_number!=11
            or state.rounds[-1].report_digest!=
               canonical_digest([x.payload() for x in destinations])):
        raise ThreatRadarError("logs must refer to exact last approved 11th-round destinations")
    record=qualify_crawler_log_handoff(
        destinations,reviewed_logs,log_reviewers,authorized=True)
    return _advance(
        state,12,"research_recorded",canonical_digest(record),
        (state.rounds[-1].report_digest,
         canonical_digest([x.body() for x in reviewed_logs])),
        reviewer,as_of,authorized=True),record


def execute_round18_adjacent_recrawl(
    state:EvolutionRun,earlier_topics:tuple[str,...],
    unresolved_topics:tuple[str,...],*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,consent:bool,
):
    if not authorized or not consent:
        raise PermissionError("independent adjacent-knowledge recrawl needs consent")
    mission=next_dragon_adjacency_mission(
        state.task,earlier_topics,unresolved_topics,
        authorized=True,consent=True)
    return _advance(
        state,18,"research_recorded",
        canonical_digest([mission.fingerprint,
                          tuple(q.terms for q in mission.queries)]),
        (state.rounds[-1].report_digest,mission.fingerprint),
        reviewer,as_of,authorized=True),mission


__all__=["execute_round3_relevance","execute_round4_shadow_backlog",
         "execute_round9_project_research",
         "derive_round11_reviewed_destinations",
         "execute_round11_destinations",
         "execute_round12_crawler_log_ingestion",
         "execute_round18_adjacent_recrawl"]
