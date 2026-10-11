"""Executable idle, structural, sandbox, and reporting stages of R3..18.

Stages without actual host-supplied game data return an explicit deferred
research/work queue. Nothing here performs a background HTTP fetch, modifies
foundation LLM weights, fabricates independent game industry assessments,
or activates a local policy. Output signatures record *what was attempted*,
not that unavailable external game work occurred.
"""
from __future__ import annotations
from dataclasses import dataclass

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError,_sha,_date
from .competitive_delivery_gate import TrustedCompetitionJudge
from .competitive_deep_analysis import ALL_FACETS
from .game_18round_evolution import EvolutionRun
from .game_18round_runtime import _advance
from .game_18round_shadow_sandbox import (
    ModularShadowTicket,SandboxVerification,sign_sandbox_verification,
    verify_shadow_in_sandbox,order_verified_hyperweights,
    verify_independent_sandbox_receipts,
)
from .game_reviewer_optimizer import OptimizationResult,OptimizerSchedule
from .game_model_promotion import PromotionStandard,PromotionError
from .game_post_weight_forensics import PostWeightReport,analyze_post_weight_change
from .game_training_flow import FlowPlan
from .competitive_mirror_training import TrainingCandidate
from .game_post_weight_dragon import PostWeightDragonMission


@dataclass(frozen=True,slots=True)
class BoundedIdleBacklog:
    round_number: int
    original_task_digest: str
    planned_topic_ids: tuple[str,...]
    max_wall_seconds: int
    max_memory_mb: int
    consumer_host_authorized: bool
    game_replays_completed: int=0
    foundation_model_trained: bool=False

    def payload(self):
        return dict(schema="skeleton.game_ai.idle_shadow_backlog.v1",
                    round_number=self.round_number,
                    original_task_digest=self.original_task_digest,
                    planned_topic_ids=list(self.planned_topic_ids),
                    max_wall_seconds=self.max_wall_seconds,
                    max_memory_mb=self.max_memory_mb,
                    consumer_host_authorized=self.consumer_host_authorized,
                    game_replays_completed=self.game_replays_completed,
                    foundation_model_trained=self.foundation_model_trained,
                    background_timer_started=False,
                    work_requires_future_host_invocation=True)


def execute_idle_round(
    state:EvolutionRun,
    shadow_tickets:tuple[ModularShadowTicket,...], *,
    reviewer:TrustedCompetitionJudge,
    as_of:str,consent:bool,authorized:bool,
    host_idle,hardware_safe,
    max_wall_seconds:int=240,
)->tuple[EvolutionRun,BoundedIdleBacklog]:
    round_no=3+len(state.rounds)
    if round_no not in {5,6}:
        raise ThreatRadarError("only explicitly designated opt-in background stages")
    if (consent is not True or not authorized or
            type(max_wall_seconds) is not int or not 5<=max_wall_seconds<=600 or
            type(shadow_tickets) is not tuple or len(shadow_tickets)>128 or
            any(not isinstance(x,ModularShadowTicket) or
                    x.task_digest!=state.task.task_digest for x in shadow_tickets)):
        raise PromotionError("bounded explicitly approved background research work needed")
    # The general knowledge stage is research scheduling only. It MUST NOT
    # silently retrofit the original project's shadow weights in idle time.
    if round_no==6:
        target=("gameplay_foundations","graphics_materials",
                "sound_accessibility","narrative_agency")
    else:
        target=tuple(x.topic_id for x in shadow_tickets)
    item=BoundedIdleBacklog(round_no,state.task.task_digest,
                            tuple(target),max_wall_seconds,
                            min(128,state.task.budget_mb//4),True)
    after=_advance(
        state,round_no,"idle_assessed",
        canonical_digest(item.payload()),
        (state.task.task_digest,
         canonical_digest([x.payload() for x in shadow_tickets])),
        reviewer,as_of,authorized=True,
        host_idle=host_idle,thermal_safe=hardware_safe,
        host_consented=True)
    return after,item


@dataclass(frozen=True,slots=True)
class ModularEraProfile:
    task_digest: str
    era: str
    genre: str
    themes: tuple[str,...]
    shadow_ids: tuple[str,...]
    quality_basis: str
    capabilities: tuple[str,...]
    reviewed_facets: int=102

    def payload(self):
        return dict(schema="skeleton.game_ai.era_genre_theme_shadow_profile.v1",
                    task_digest=self.task_digest,era=self.era,genre=self.genre,
                    themes=list(self.themes),shadow_ids=list(self.shadow_ids),
                    quality_basis=self.quality_basis,
                    capabilities=list(self.capabilities),
                    reviewed_facets=self.reviewed_facets,
                    auto_code_edits=False)


def execute_round7_era_profile(
    state:EvolutionRun,tickets:tuple[ModularShadowTicket,...],*,
    reviewer:TrustedCompetitionJudge,as_of:str,authorized:bool,
)->tuple[EvolutionRun,ModularEraProfile]:
    if not authorized:raise PermissionError("era/genre shadow modules need studio authority")
    if len(ALL_FACETS)!=102:
        raise ThreatRadarError("full 102-facet professional coding and game rubric lost")
    selected=tuple(sorted(t.ticket_id for t in tickets
                          if t.task_digest==state.task.task_digest
                          and state.task.era in t.eras
                          and state.task.genre in t.genres))
    profile=ModularEraProfile(
        state.task.task_digest,state.task.era,state.task.genre,
        state.task.themes,selected,
        "102_source_reviewed_game_scrutiny_facets",state.task.capabilities)
    return _advance(
        state,7,"shadow_queued",canonical_digest(profile.payload()),
        (state.task.task_digest,
         canonical_digest([x.payload() for x in tickets])),
        reviewer,as_of,authorized=True),profile


@dataclass(frozen=True,slots=True)
class IndustryEngineeringGate:
    task_digest: str
    reviewed_code_digest: str
    quality_axes: tuple[str,...]
    minimum_facet_coverage: int
    exact_build_requirement: str
    quality_certified: bool=False

    def payload(self):
        return dict(schema="skeleton.game_ai.game_creation_professional_gate.v1",
                    task_digest=self.task_digest,
                    reviewed_code_digest=self.reviewed_code_digest,
                    quality_axes=list(self.quality_axes),
                    minimum_facet_coverage=self.minimum_facet_coverage,
                    exact_build_requirement=self.exact_build_requirement,
                    quality_certified=self.quality_certified,
                    benchmark_results_required=True)


def execute_round8_engineering_gate(
    state:EvolutionRun,reviewed_code_digest:str,*,
    reviewer:TrustedCompetitionJudge,as_of:str,authorized:bool,
)->tuple[EvolutionRun,IndustryEngineeringGate]:
    if not authorized:raise PermissionError("game industry operational gate needs reviewed original code")
    _sha(reviewed_code_digest)
    standards=IndustryEngineeringGate(
        state.task.task_digest,reviewed_code_digest,
        ("maintainability","deterministic_replay","code_security",
         "visual_frame_tail","audio_caption_parity","player_accessibility",
         "originality","npc_epistemic_causality",
         "hardware_memory","story_continuity",
         "cross_platform_builds","independent_user_quality"),102,
        "reproducible_original_binary_and_signed_device_replay")
    return _advance(
        state,8,"reviewed",canonical_digest(standards.payload()),
        (reviewed_code_digest,state.task.task_digest),
        reviewer,as_of,authorized=True),standards


@dataclass(frozen=True,slots=True)
class ProjectCrawlerTargetBrief:
    task_digest: str
    dragon_mission_fingerprint: str
    source_research_digest: str
    target_genre: str
    target_era: str
    original_capabilities: tuple[str,...]
    research_topics: tuple[str,...]
    evidence_policy: tuple[str,...]
    newly_fetched_sources: int=0

    def payload(self):
        return dict(schema="skeleton.game_ai.project_crawler_target_brief.v1",
                    task_digest=self.task_digest,
                    dragon_mission_fingerprint=self.dragon_mission_fingerprint,
                    source_research_digest=self.source_research_digest,
                    target_genre=self.target_genre,target_era=self.target_era,
                    original_capabilities=list(self.original_capabilities),
                    research_topics=list(self.research_topics),
                    evidence_policy=list(self.evidence_policy),
                    newly_fetched_sources=self.newly_fetched_sources)


def execute_round10_crawler_brief(
    state:EvolutionRun,
    mission:PostWeightDragonMission,*,
    reviewer:TrustedCompetitionJudge,as_of:str,
    authorized:bool,
)->tuple[EvolutionRun,ProjectCrawlerTargetBrief]:
    if not authorized:raise PermissionError("the user must authorize this scoped crawler target")
    if (len(state.rounds)<7 or state.rounds[-1].round_number!=9
            or state.rounds[-1].report_digest!=canonical_digest(mission.payload())):
        raise ThreatRadarError("round10 must summarize the exact preceding Dragon source mission")
    draft=ProjectCrawlerTargetBrief(
        state.task.task_digest,mission.native_mission.fingerprint,
        mission.source_report_digest,state.task.genre,state.task.era,
        state.task.capabilities,mission.topics,
        ("current_wiki_revision","human_source_review",
         "rights_reference_vs_training","independent_publisher_groups",
         "no_heldout_game_labels","no_copyrighted_assets","authorized_safe_http"))
    return _advance(
        state,10,"research_recorded",canonical_digest(draft.payload()),
        (mission.source_report_digest,mission.native_mission.fingerprint),
        reviewer,as_of,authorized=True),draft


def execute_round13_sandbox(
    state:EvolutionRun,ticket:ModularShadowTicket,
    plan:FlowPlan,standard:PromotionStandard,
    champion:dict|None,
    usage:tuple[TrainingCandidate,...],idle:tuple[TrainingCandidate,...],*,
    reviewer:TrustedCompetitionJudge,
    independent_verifier:TrustedCompetitionJudge,
    as_of:str,authorized:bool,consent:bool,
    professional_code_review_approved:bool,
    professional_code_review_digest:str,
    schedule:OptimizerSchedule=OptimizerSchedule(
        learning_rates=(0.12,),epochs=(10,),max_trials=1),
):
    if not authorized or not consent:
        raise PermissionError("adversarial actual reviewer sandbox needs active operator consent")
    verdict,model=verify_shadow_in_sandbox(
        ticket,plan,standard,champion,usage,idle,authorized=True,
        consent=True,original_code_quality_approved=professional_code_review_approved,
        original_code_quality_receipt=professional_code_review_digest,
        schedule=schedule)
    if verdict.permission_to_stage:
        signed=sign_sandbox_verification(verdict,independent_verifier)
        state=_advance(
            state,13,"verified_sandbox",signed.digest,
            (ticket.digest,canonical_digest(plan.payload())),
            reviewer,as_of,authorized=True,
            shadow_proof=signed,shadow_verifier=independent_verifier)
        return state,signed,model
    state=_advance(state,13,"blocked",
                   canonical_digest(verdict.payload()),
                   (ticket.digest,canonical_digest(plan.payload())),
                   reviewer,as_of,authorized=True)
    return state,verdict,model


def execute_round14_weight_forensics(
    state:EvolutionRun,original_games:FlowPlan,
    optimization:OptimizationResult,
    standard:PromotionStandard,champion:dict|None,*,
    reviewer:TrustedCompetitionJudge,
    as_of:str,authorized:bool,
)->tuple[EvolutionRun,PostWeightReport]:
    if not authorized:raise PermissionError("actual post-candidate weight scrutiny needs operator")
    evidence=analyze_post_weight_change(
        original_games,optimization,standard=standard,champion=champion,
        authorized=True)
    status="reviewed" if evidence.shadow_fit_qualified else "blocked"
    return _advance(
        state,14,status,evidence.digest,
        (evidence.plan_digest,evidence.model_after_digest),
        reviewer,as_of,authorized=True),evidence


@dataclass(frozen=True,slots=True)
class WeightStructureReport:
    task_digest: str
    staged_candidates: tuple[str,...]
    research_only_candidates: tuple[str,...]
    recent_model_digest: str|None
    structure: tuple[str,...]
    foundation_model_weights_modified: bool=False

    def payload(self):
        return dict(schema="skeleton.game_ai.modular_weight_structure_report.v1",
                    task_digest=self.task_digest,
                    staged_candidates=list(self.staged_candidates),
                    research_only_candidates=list(self.research_only_candidates),
                    recent_model_digest=self.recent_model_digest,
                    structure=list(self.structure),
                    foundation_model_weights_modified=self.foundation_model_weights_modified,
                    human_installation_required=True)


def execute_round15_structure(
    state:EvolutionRun,tickets:tuple[ModularShadowTicket,...],
    verified:tuple[SandboxVerification,...],*,
    reviewer:TrustedCompetitionJudge,as_of:str,authorized:bool,
    verifiers:tuple[TrustedCompetitionJudge,...]=(),
)->tuple[EvolutionRun,WeightStructureReport]:
    if not authorized:raise PermissionError("model structure needs approved original game review")
    verify_independent_sandbox_receipts(verified,verifiers,authorized=True)
    by_id={x.ticket_id:x for x in verified}
    if len(by_id)!=len(verified):
        raise PromotionError("duplicate post-weight candidate proof is not extra competence")
    used=[]
    waiting=[]
    policies=[]
    for ticket in tickets:
        if ticket.task_digest!=state.task.task_digest:
            raise PromotionError("cannot reorganize another project's knowledge weights")
        receipt=by_id.get(ticket.ticket_id)
        if receipt and receipt.permission_to_stage and not receipt.blockers:
            used.append(ticket.ticket_id)
            if receipt.model_digest:policies.append(receipt.model_digest)
        else:waiting.append(ticket.ticket_id)
    summary=WeightStructureReport(
        state.task.task_digest,tuple(sorted(used)),
        tuple(sorted(waiting)),
        canonical_digest(sorted(policies)) if policies else None,
        ("reference_only_Wiki_almanac","original_game_train_candidates",
         "frozen_validation_and_test","verified_shadow_adapters",
         "on_demand_era_genre_theme_loads","operator_model_registry_activation"))
    return _advance(
        state,15,"shadow_queued",canonical_digest(summary.payload()),
        (state.task.task_digest,
         canonical_digest([x.payload() for x in tickets])),
        reviewer,as_of,authorized=True),summary


def execute_round16_load_order(
    state:EvolutionRun,tickets:tuple[ModularShadowTicket,...],
    proofs:tuple[SandboxVerification,...],*,
    reviewer:TrustedCompetitionJudge,as_of:str,authorized:bool,
    verifiers:tuple[TrustedCompetitionJudge,...]=(),
):
    if not authorized:raise PermissionError("priority-weight queue needs authorized user objective")
    ordered=order_verified_hyperweights(state.task,tickets,proofs,
                                        authorized=True,verifiers=verifiers)
    return _advance(
        state,16,"shadow_queued",
        canonical_digest(ordered.payload()),
        (state.task.task_digest,
         canonical_digest([x.payload() for x in proofs]) or "0"*64),
        reviewer,as_of,authorized=True),ordered


@dataclass(frozen=True,slots=True)
class AcquiredWeightStatusReport:
    task_digest: str
    historic_rounds: tuple[int,...]
    source_research_events: int
    queued_shadow_events: int
    approved_sandbox_events: int
    genuine_model_improvement_claims: int
    unresolved_rounds: int
    last_forensic_digest: str|None
    no_core_weights_installed: bool=True

    def payload(self):
        return dict(schema="skeleton.game_ai.18round_weight_acquisition_report.v1",
                    task_digest=self.task_digest,
                    historic_rounds=list(self.historic_rounds),
                    source_research_events=self.source_research_events,
                    queued_shadow_events=self.queued_shadow_events,
                    approved_sandbox_events=self.approved_sandbox_events,
                    genuine_model_improvement_claims=self.genuine_model_improvement_claims,
                    unresolved_rounds=self.unresolved_rounds,
                    last_forensic_digest=self.last_forensic_digest,
                    no_core_weights_installed=self.no_core_weights_installed,
                    model_bytes_deployed=False)


def execute_round17_report(
    state:EvolutionRun,post_weights:PostWeightReport|None,*,
    reviewer:TrustedCompetitionJudge,as_of:str,authorized:bool,
)->tuple[EvolutionRun,AcquiredWeightStatusReport]:
    if not authorized:raise PermissionError("verified industry code/model weight report needs operator")
    round_numbers=tuple(r.round_number for r in state.rounds)
    report=AcquiredWeightStatusReport(
        state.task.task_digest,round_numbers,
        sum(r.status=="research_recorded" for r in state.rounds),
        sum(r.status=="shadow_queued" for r in state.rounds),
        sum(r.status=="verified_sandbox" for r in state.rounds),
        sum(r.status=="verified_sandbox" for r in state.rounds),
        sum(r.status=="blocked" for r in state.rounds),
        post_weights.digest if post_weights else None)
    return _advance(
        state,17,"research_recorded",
        canonical_digest(report.payload()),
        (state.task.task_digest,
         post_weights.digest if post_weights else state.task.original_design_digest),
        reviewer,as_of,authorized=True),report

__all__=["BoundedIdleBacklog","execute_idle_round",
         "ModularEraProfile","execute_round7_era_profile",
         "IndustryEngineeringGate","execute_round8_engineering_gate",
         "ProjectCrawlerTargetBrief","execute_round10_crawler_brief",
         "execute_round13_sandbox","execute_round14_weight_forensics",
         "WeightStructureReport","execute_round15_structure",
         "execute_round16_load_order",
         "AcquiredWeightStatusReport","execute_round17_report"]
