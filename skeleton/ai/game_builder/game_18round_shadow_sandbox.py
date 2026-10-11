"""Isolated rounds 4-8, 13-16: modular original-game shadow weights.

A 'hyperweight' is a *loadable local reviewer-policy/adapter reference*,
not secretly changed core LLM parameters. Reference-only research can
change topic priority and original-game test plans, NEVER weight bytes.
Real weight optimization runs through the existing TRAIN-only SGD and sealed
validation/test quality gates. Afterward, TWO fresh original-game usage and
idle cohorts may independently challenge the frozen candidate. An operator
must separately stage and activate it through ReviewerRegistry.

The sandbox never trusts a caller-supplied boolean saying improvement passed:
it recomputes actual numerical heldout, calibration, project/attack-family
deltas and the exact policy digest. It is entirely offline and deterministic
given external independently replayed source data.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from math import isfinite
import hmac

from .contracts import canonical_digest
from .game_18round_relevance import OriginalTaskFocus,TopicPriority
from .game_training_flow import FlowPlan
from .game_model_promotion import (
    PromotionError,PromotionStandard,validate_policy,
    evaluate_fresh_cohort,
)
from .game_reviewer_optimizer import (
    OptimizerSchedule,OptimizationResult,optimize_review_weights,
)
from .game_post_weight_forensics import PostWeightReport,analyze_post_weight_change
from .game_learning_feedback import feedback_from_cohort
from .competitive_mirror_training import TrainingCandidate
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .competitive_title_radar import _sha,_id,_date


@dataclass(frozen=True,slots=True)
class ModularShadowTicket:
    ticket_id: str
    task_digest: str
    topic_id: str
    priority_bp: int
    requested_memory_mb: int
    eras: tuple[str,...]
    genres: tuple[str,...]
    themes: tuple[str,...]
    source_almanac_digest: str
    original_code_review_digest: str
    original_game_plan_digest: str
    operator_requested: bool
    stage: str="queued"
    weight_policy_digest: str|None=None

    def __post_init__(self):
        for name in (self.ticket_id,self.topic_id):_id(getattr(self,name),"shadow ticket")
        for d in (self.task_digest,self.source_almanac_digest,
                  self.original_code_review_digest,self.original_game_plan_digest):_sha(d)
        if (type(self.priority_bp) is not int or not 0<=self.priority_bp<=10000 or
                type(self.requested_memory_mb) is not int or
                not 1<=self.requested_memory_mb<=2048 or
                self.operator_requested is not True):
            raise PromotionError("bounded opted-in hyperweight memory and empirical usefulness")
        for seq in (self.eras,self.genres,self.themes):
            if type(seq) is not tuple or len(seq)>24 or len(set(seq))!=len(seq):
                raise PromotionError("specific era/genre/theme modules, not wildcard priorities")
        if self.stage not in {"queued","sandbox_verified","blocked","rejected"}:
            raise PromotionError("no direct active-weight or unsandboxed promotion status")
        if self.weight_policy_digest is not None:_sha(self.weight_policy_digest)

    @property
    def digest(self):
        return canonical_digest(self.payload())
    def payload(self):
        return dict(schema="skeleton.game_ai.modular_shadow_ticket.v1",
                    ticket_id=self.ticket_id,task_digest=self.task_digest,
                    topic_id=self.topic_id,priority_bp=self.priority_bp,
                    requested_memory_mb=self.requested_memory_mb,
                    eras=list(self.eras),genres=list(self.genres),themes=list(self.themes),
                    source_almanac_digest=self.source_almanac_digest,
                    original_code_review_digest=self.original_code_review_digest,
                    original_game_plan_digest=self.original_game_plan_digest,
                    operator_requested=self.operator_requested,stage=self.stage,
                    weight_policy_digest=self.weight_policy_digest,
                    foundation_parameters_modified=False,
                    automatically_activated=False)


def prepare_shadow_tickets(
    task: OriginalTaskFocus,
    priorities:tuple[TopicPriority,...],plan:FlowPlan, *,
    original_code_review_digest:str,
    allocated_memory_mb:int,
    authorized:bool,
)->tuple[ModularShadowTicket,...]:
    if not authorized:raise PermissionError("modular shadow backlog needs owner authority")
    _sha(original_code_review_digest,"source-owned game code quality review")
    if (not isinstance(task,OriginalTaskFocus) or not isinstance(plan,FlowPlan)
            or type(priorities) is not tuple
            or any(not isinstance(p,TopicPriority) for p in priorities)
            or type(allocated_memory_mb) is not int
            or not 1<=allocated_memory_mb<=min(task.budget_mb//4,4096)):
        raise PromotionError("bounded real original-game training and memory plan")
    seen=set()
    result=[]
    remaining=allocated_memory_mb
    for priority in sorted(priorities,key=lambda r:(-r.estimated_usefulness_bp,r.topic_id)):
        if priority.topic_id in seen:raise PromotionError("repeated knowledge topic creates false queue volume")
        seen.add(priority.topic_id)
        if priority.mode!="experimental_shadow_candidate" or priority.estimated_usefulness_bp<500:
            continue
        # Policy is fixed-size and needs bounded headroom for projected
        # post-training metrics; memory accounting remains conservative.
        size=4
        if size>remaining:break
        remaining-=size
        result.append(ModularShadowTicket(
            canonical_digest([task.task_digest,priority.topic_digest,"shadow"]),
            task.task_digest,priority.topic_id,priority.estimated_usefulness_bp,
            size,(task.era,),(task.genre,),task.themes,
            priority.topic_digest,original_code_review_digest,
            canonical_digest(plan.payload()),True))
    return tuple(result)


@dataclass(frozen=True,slots=True)
class FreshSandboxEvidence:
    cohort_mode: str
    output: dict
    source_plan_digest: str

    def payload(self):
        return dict(cohort_mode=self.cohort_mode,
                    output=self.output,source_plan_digest=self.source_plan_digest)


@dataclass(frozen=True,slots=True)
class SandboxVerification:
    ticket_id: str
    model_digest: str|None
    incumbent_digest: str|None
    first_weight_forensic_digest: str|None
    source_plan_digest: str
    standard_digest: str
    verified_cohorts: tuple[FreshSandboxEvidence,...]
    blockers: tuple[str,...]
    code_quality_reviewed: bool
    strict_measured_gain: bool
    permission_to_stage: bool
    model_activation_performed: bool=False

    @property
    def digest(self):return canonical_digest(self.payload())
    def payload(self):
        return dict(schema="skeleton.game_ai.shadow_weight_verification_sandbox.v1",
                    ticket_id=self.ticket_id,model_digest=self.model_digest,
                    incumbent_digest=self.incumbent_digest,
                    first_weight_forensic_digest=self.first_weight_forensic_digest,
                    source_plan_digest=self.source_plan_digest,
                    standard_digest=self.standard_digest,
                    verified_cohorts=[x.payload() for x in self.verified_cohorts],
                    blockers=list(self.blockers),
                    code_quality_reviewed=self.code_quality_reviewed,
                    strict_measured_gain=self.strict_measured_gain,
                    permission_to_stage=self.permission_to_stage,
                    model_activation_performed=self.model_activation_performed,
                    authorized_to_modify_core_llm_weights=False,
                    verified_not_installed=True)


def verify_shadow_in_sandbox(
    ticket:ModularShadowTicket,plan:FlowPlan,standard:PromotionStandard,
    champion:dict|None,
    usage:tuple[TrainingCandidate,...],
    idle:tuple[TrainingCandidate,...], *,
    authorized:bool,consent:bool,
    original_code_quality_approved:bool,
    original_code_quality_receipt:str,
    schedule:OptimizerSchedule=OptimizerSchedule(
        learning_rates=(0.12,),epochs=(10,),max_trials=1),
)->tuple[SandboxVerification,OptimizationResult|None]:
    if not authorized or not consent:
        raise PermissionError("isolated original game model experiments require explicit host consent")
    _sha(original_code_quality_receipt,"approved industry code review")
    if (not isinstance(ticket,ModularShadowTicket)
            or not isinstance(plan,FlowPlan)
            or not isinstance(standard,PromotionStandard)
            or not isinstance(schedule,OptimizerSchedule)
            or ticket.stage!="queued"
            or ticket.original_game_plan_digest!=canonical_digest(plan.payload())
            or ticket.original_code_review_digest!=original_code_quality_receipt
            or type(original_code_quality_approved) is not bool):
        raise PromotionError("stale queue, wrong code review, unqualified or unsafe original game")
    if champion is not None:validate_policy(champion)
    blockers=[]
    if not original_code_quality_approved:blockers.append("unreviewed_original_game_code_quality")
    if champion is None:blockers.append("no_installed_champion_for_proven_uplift")
    if not usage or not idle:blockers.append("missing_fresh_usage_or_idle_cohort")
    if len({x.project_digest for x in usage}&{x.project_digest for x in idle}):
        raise PromotionError("usage and idle observation projects must be disjoint")
    prior=set(plan.source_projects)
    if any(x.project_digest in prior for x in (*usage,*idle)):
        raise PromotionError("sandbox cannot reuse TRAIN, validation or sealed TEST worlds")
    if blockers:
        return SandboxVerification(ticket.ticket_id,None,
            canonical_digest(champion) if champion else None,None,
            canonical_digest(plan.payload()),standard.digest,(),
            tuple(sorted(blockers)),original_code_quality_approved,False,False),None
    selected=optimize_review_weights(
        plan,authorized=True,schedule=schedule,standard=standard,
        champion=champion)
    forensic=analyze_post_weight_change(
        plan,selected,standard=standard,champion=champion,authorized=True)
    if not forensic.shadow_fit_qualified or not selected.candidate_improved:
        blockers.extend(forensic.safety_objections)
        blockers.append("no_qualified_heldout_model_improvement")
    cohort_reports=[]
    for mode,rows in (("usage",usage),("idle",idle)):
        out=evaluate_fresh_cohort(
            rows,selected.selected_fit["symbolic_policy"],standard=standard,
            source_projects=tuple(plan.source_projects),champion=champion,
            authorized=True)
        cohort_reports.append(FreshSandboxEvidence(
            mode,out,canonical_digest(plan.payload())))
        if not out["passed"]:blockers.append(mode+":failed_fresh_game_cohort")
        # Strict uplift on independent gameplay, not merely 'within'
        # tolerated regression against the champion.
        prev=out["champion_comparison"]
        curr=out["metrics"]
        if (prev is None or curr["balanced_accuracy"]+1e-6<
                prev["balanced_accuracy"] or
                curr["brier"]>prev["brier"]+1e-8):
            blockers.append(mode+":actual_model_quality_regression")
    verified=not blockers
    return SandboxVerification(
        ticket.ticket_id,selected.selected_fit["fitted_policy_digest"],
        canonical_digest(champion),forensic.digest,
        canonical_digest(plan.payload()),standard.digest,
        tuple(cohort_reports),tuple(sorted(set(blockers))),
        original_code_quality_approved,verified,verified),selected


@dataclass(frozen=True,slots=True)
class HyperweightLoadOrder:
    task_digest: str
    cached_ticket_ids: tuple[str,...]
    deferred_ticket_ids: tuple[str,...]
    planned_mb: int
    budget_mb: int
    verified_tickets: int
    ordered_digests: tuple[str,...]

    def payload(self):
        return dict(schema="skeleton.game_ai.ordered_verified_hyperweight_queue.v1",
                    task_digest=self.task_digest,
                    cached_ticket_ids=list(self.cached_ticket_ids),
                    deferred_ticket_ids=list(self.deferred_ticket_ids),
                    planned_mb=self.planned_mb,budget_mb=self.budget_mb,
                    verified_tickets=self.verified_tickets,
                    ordered_digests=list(self.ordered_digests),
                    weights_actually_installed=False,
                    task_relevance_queue_not_foundation_model_gradients=True)

def order_verified_hyperweights(
    task:OriginalTaskFocus,tickets:tuple[ModularShadowTicket,...],
    verified:tuple[SandboxVerification,...],*,authorized:bool,
)->HyperweightLoadOrder:
    if not authorized:raise PermissionError("load ordering needs authorized task")
    if not isinstance(task,OriginalTaskFocus) or type(tickets) is not tuple or type(verified) is not tuple:
        raise PromotionError("typed task and qualified original-game policy references required")
    receipts={x.ticket_id:x for x in verified}
    if len(receipts)!=len(verified):raise PromotionError("duplicate sandbox verdict")
    selected=[];waiting=[];used=0
    for row in sorted(tickets,key=lambda x:(-x.priority_bp,x.requested_memory_mb,x.ticket_id)):
        if row.task_digest!=task.task_digest:raise PromotionError("cross-game hyperweight reference")
        witness=receipts.get(row.ticket_id)
        if not witness or not witness.permission_to_stage or witness.blockers:
            waiting.append(row.ticket_id);continue
        if used+row.requested_memory_mb>task.budget_mb//4:
            waiting.append(row.ticket_id);continue
        selected.append(row.ticket_id);used+=row.requested_memory_mb
    return HyperweightLoadOrder(task.task_digest,tuple(selected),tuple(waiting),
                                used,task.budget_mb//4,len(selected),
                                tuple(row.digest for row in tickets))
__all__=["ModularShadowTicket","prepare_shadow_tickets","FreshSandboxEvidence",
         "SandboxVerification","verify_shadow_in_sandbox",
         "HyperweightLoadOrder","order_verified_hyperweights"]
