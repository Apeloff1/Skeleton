"""Machine-actionable original game delivery campaign under rival pressure.

This converts each credible ENEMY overlap into concrete owned quality work.
It does NOT spoof AI agent execution: dispatch is a typed execution request
for the existing forge or a future authenticated Jeeves/Dragon service.
Completion requires external original-game receipts AND the existing
independently reviewed competitive delivery gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .contracts import QUALITY_AXES, PROTECTED_AXES, canonical_digest
from .rival_convergence_observatory import (
    PlannedTitle, ConvergenceReport, DeliveryVerification,
    verify_delivery, CompetitiveError,
)

# The consumer-visible game-production sequence must not allow a polished but
# unoriginal imitation to bypass evidence, authorship, platform or legal review.
STAGES=(
    ("wiki","source_and_benchmark", "Acquire independent public references, comparable benchmark protocols and rights-cleared background evidence."),
    ("jeeves","original_game_design","Produce an original implementation design preserving signature, player fantasy, era and genre intent; no copied expressive treatment."),
    ("builder","implement_and_optimize","Implement original gameplay, optimize resource use, and build tangible playable content—not only evaluation scaffolding."),
    ("adversarial_mirror","attempt_to_break","Attack playability, edge cases, coherence, regressions, platform behavior, exploits, originality and false evidence."),
    ("hoag","player_polish","Conduct independent playable human/automated accessibility, usability, aesthetic and pacing reviews; improve tangible experience."),
    ("rights_wiki","verify_and_release","Obtain fresh source and rights clearance, comparable quality proof and explicit authorized release gate."),
)


@dataclass(frozen=True,slots=True)
class CompetitiveTask:
    task_id: str
    order_id: str
    project_id: str
    competitor_id: str
    axis: str
    lane: str
    stage: str
    prerequisite_task_ids: tuple[str,...]
    expected_evidence: str
    priority: int
    source_report_digest: str
    protected_identity_digest: str

    def payload(self):
        return {name:(list(getattr(self,name)) if name=="prerequisite_task_ids"
                      else getattr(self,name))
                for name in self.__dataclass_fields__}


@dataclass(frozen=True,slots=True)
class CompetitiveCampaign:
    plan_digest: str
    report_digest: str
    protected_identity_digest: str
    tasks: tuple[CompetitiveTask,...]
    open_orders: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        body=dict(schema="skeleton.game_builder.rival_delivery_campaign.v1",
                  plan_digest=self.plan_digest,report_digest=self.report_digest,
                  protected_identity_digest=self.protected_identity_digest,
                  tasks=[t.payload() for t in self.tasks],
                  open_orders=list(self.open_orders),
                  every_credible_axis_gets_real_delivery_work=True,
                  competitor_assets_or_protected_eval_cases_copied=False,
                  actual_execution_or_model_training=False,
                  release_requires_external_verified_game_evidence=True)
        return {**body,"campaign_digest":canonical_digest(body)}


def plan_competitive_campaign(plan: PlannedTitle,report: ConvergenceReport,
                              *,authorized:bool)->CompetitiveCampaign:
    if not authorized:
        raise PermissionError("rival pressure plan requires authorized original creator")
    if not isinstance(plan,PlannedTitle) or not isinstance(report,ConvergenceReport):
        raise CompetitiveError("typed reviewed original title and convergence report required")
    if report.original_plan_digest!=plan.digest or report.project_id!=plan.project_id:
        raise CompetitiveError("refuse to redirect work to a rival's game identity")
    if report.status!="enemy":
        if report.orders:
            raise CompetitiveError("non-enemy cannot impose unverified competitive orders")
        return CompetitiveCampaign(plan.digest,report.digest,
                                   plan.distinctive_signature_digest,(),())
    if (len(report.orders)<2 or len(report.orders)>len(QUALITY_AXES)+1
            or any(o.project_id!=plan.project_id or
                   o.rival_title_id!=report.competitor_id or
                   o.protected_identity_digest!=plan.distinctive_signature_digest
                   for o in report.orders)
            or len({o.order_id for o in report.orders})!=len(report.orders)
            or not any(o.axis=="originality" and
                       o.kind=="protect_individuality" for o in report.orders)):
        raise CompetitiveError("full original-identity and bounded competing-title campaign required")
    tasks=[]
    orders=[]
    for order in sorted(report.orders,key=lambda x:(-x.priority,x.axis,x.order_id)):
        prior=()
        orders.append(order.order_id)
        for lane,stage,request in STAGES:
            details=(
                f"{request} Axis={order.axis}; order={order.kind}; "
                f"measured_target={order.minimum_measured_score if order.minimum_measured_score is not None else 'independent_benchmark_required'}; "
                f"original_pillars={','.join(plan.original_identity_pillars)}; "
                f"independent_citation_digest={order.reference_evidence_digest}."
            )
            task_body=dict(
                order_id=order.order_id,project_id=plan.project_id,
                competitor_id=report.competitor_id,axis=order.axis,
                lane=lane,stage=stage,prerequisite_task_ids=list(prior),
                expected_evidence=details,priority=order.priority,
                source_report_digest=report.digest,
                protected_identity_digest=plan.distinctive_signature_digest)
            task_id=canonical_digest(task_body)
            tasks.append(CompetitiveTask(
                task_id=task_id,order_id=order.order_id,
                project_id=plan.project_id,competitor_id=report.competitor_id,
                axis=order.axis,lane=lane,stage=stage,
                prerequisite_task_ids=prior,expected_evidence=details,
                priority=order.priority,source_report_digest=report.digest,
                protected_identity_digest=plan.distinctive_signature_digest))
            prior=(task_id,)
    return CompetitiveCampaign(plan.digest,report.digest,
                               plan.distinctive_signature_digest,
                               tuple(tasks),tuple(orders))


@dataclass(frozen=True,slots=True)
class TaskEvidence:
    task_id: str
    evidence_digest: str
    actor_id: str
    original_game_digest: str
    approved_by_independent_reviewer: bool
    protected_identity_digest: str

    def __post_init__(self):
        from .rival_convergence_observatory import _hash,_ident
        _hash(self.task_id,"exact task identity")
        _hash(self.evidence_digest,"completed task evidence")
        _ident(self.actor_id,"replay/worker actor")
        _hash(self.original_game_digest,"replayed original game")
        _hash(self.protected_identity_digest,"unchanged signature")
        if type(self.approved_by_independent_reviewer) is not bool:
            raise CompetitiveError("review must be explicitly affirmed")

    def payload(self):
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


def reconcile_competitive_campaign(
    plan:PlannedTitle,report:ConvergenceReport,campaign:CompetitiveCampaign,
    evidence:tuple[TaskEvidence,...],verification:DeliveryVerification|None,
    *,authorized:bool
)->dict:
    if not authorized:
        raise PermissionError("campaign cannot be promoted without trusted operator")
    if not isinstance(campaign,CompetitiveCampaign) or type(evidence) is not tuple:
        raise CompetitiveError("typed complete competitive evidence required")
    required=plan_competitive_campaign(plan,report,authorized=True)
    if campaign.digest!=required.digest or campaign.payload()!=required.payload():
        raise CompetitiveError("campaign was modified or dropped costly quality stages")
    if len(evidence)>len(campaign.tasks) or any(not isinstance(x,TaskEvidence) for x in evidence):
        raise CompetitiveError("bounded typed task receipt set required")
    byid={e.task_id:e for e in evidence}
    if len(byid)!=len(evidence):
        raise CompetitiveError("reused task receipt does not show repetitive delivery work")
    checked=set()
    blockers=[]
    for task in campaign.tasks:
        item=byid.get(task.task_id)
        if item is None:
            blockers.append(f"unfinished:{task.task_id}")
            continue
        if (item.protected_identity_digest!=plan.distinctive_signature_digest
                or item.original_game_digest==report.signal_root):
            blockers.append(f"unoriginal_or_wrong_game:{task.task_id}")
            continue
        if not item.approved_by_independent_reviewer:
            blockers.append(f"not_independently_reviewed:{task.task_id}")
            continue
        if any(dep not in checked for dep in task.prerequisite_task_ids):
            blockers.append(f"prerequisite_unfinished:{task.task_id}")
            continue
        checked.add(task.task_id)
    extras=set(byid)-{t.task_id for t in campaign.tasks}
    if extras:
        raise CompetitiveError("unknown noncampaign receipt cannot close rival workload")
    if verification is None:
        blockers.append("independent_release_evidence_not_submitted")
        release=None
    else:
        release=verify_delivery(plan,report,verification,authorized=True)
        blockers.extend(f"release:{v}" for v in release["blockers"])
    return dict(
        schema="skeleton.game_builder.competitive_campaign_reconciliation.v1",
        campaign_digest=campaign.digest,report_digest=report.digest,
        task_count=len(campaign.tasks),accepted_task_receipts=len(checked),
        incomplete_task_count=len(campaign.tasks)-len(checked),
        status="qualified_for_operator_release_decision" if not blockers
             else "work_required",
        blockers=sorted(set(blockers)),
        release_evaluation=release,
        original_signature_unchanged=plan.distinctive_signature_digest,
        automatic_release=False,
    )


__all__=["STAGES","CompetitiveTask","CompetitiveCampaign",
         "TaskEvidence","plan_competitive_campaign",
         "reconcile_competitive_campaign"]
