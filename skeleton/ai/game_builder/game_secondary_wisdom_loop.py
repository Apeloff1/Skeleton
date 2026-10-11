"""Independent second glance: repeated knowledge digestion -> reviewed research -> new weights.

Three distinct comprehension passes:
  1) decomposition and source-authentic interpretation;
  2) adversarial reversal and independent counterexamples;
  3) cross-era transfer and separately proofread original-game experiments.

Every pass is signed by *three different configured* Dragon/Jeeves/Adversarial
review identities, bound to the same newly acquired CURRENT Wiki rights
packet and to individual role-specific examined tasks. A signature proves
configured key possession, not that a named foundation model actually ran.
Original articles, game videos and blog text NEVER enter local gradients.

A secondary model update can happen only from a fresh, independently authored
TRAIN/validation/test project plan that shares ZERO source projects with the
first evaluation. The real local reviewer SGD is run a second time and fully
re-evaluated on its sealed holdouts, with a candidate reference comparison.
No LLM parameter update or promotion/activation occurs in this module.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
import hmac

from .contracts import canonical_digest
from .game_dragon_peer_wisdom import (
    DragonWisdomAlmanac,SourceMediaReceipt,distill_dragon_peer_wisdom,
)
from .game_post_weight_forensics import (
    PostWeightReport,analyze_post_weight_change,
)
from .game_post_weight_dragon import PostWeightDragonMission
from .game_integrated_learning import (
    IntegratedLearningCycle,run_integrated_learning_cycle,
)
from .game_reviewer_optimizer import OptimizerSchedule
from .game_model_promotion import PromotionError,PromotionStandard
from .game_training_flow import FlowPlan
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger,UseKind,RightsState
from .competitive_title_radar import _date,_sha,_id

ROLES=("dragon","jeeves","adversarial")
ANGLES=(
    ("decomposition",
     "Separate each abstract source claim into assumptions, measurement "
     "limits, original game mechanics and permissible derived ideas.",
     "Detect paraphrase drift, rights misclassification and false peer independence."),
    ("adversarial_reversal",
     "Attempt to disprove each previous interpretation through contrary "
     "independent papers, negative gameplay controls and missing data.",
     "Detect contradictory sources, causal confounding and overconfident conclusions."),
    ("second_wisdom",
     "Transfer only independently reconfirmed abstractions into fresh "
     "original-game TRAIN projects while preserving unseen holdout groups.",
     "Detect replay leakage, post-weight regressions and originality failures."),
)


@dataclass(frozen=True,slots=True)
class DigestionTask:
    round_number: int
    mechanic: str
    wisdom_angle: str
    prior_almanac_digest: str
    new_almanac_digest: str
    source_research_digest: str
    hypothesis: str
    disconfirmation: str
    rights_training_firewall: str="reference_research_only"

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.second_wisdom_task.v1",
            round_number=self.round_number,mechanic=self.mechanic,
            wisdom_angle=self.wisdom_angle,
            prior_almanac_digest=self.prior_almanac_digest,
            new_almanac_digest=self.new_almanac_digest,
            source_research_digest=self.source_research_digest,
            hypothesis=self.hypothesis,
            disconfirmation=self.disconfirmation,
            rights_training_firewall=self.rights_training_firewall,
            no_training_from_copyright_reference_media=True)


@dataclass(frozen=True,slots=True)
class WisdomPassAttestation:
    role: str
    round_number: int
    task_digests: tuple[str,...]
    research_packet_digest: str
    first_weight_audit_digest: str
    proofread_output_digest: str
    proofread_checks: tuple[str,...]
    adversarial_objection_count: int
    unresolved_source_conflicts: int
    quality_bp: int
    reviewer_id: str
    reviewed_at: str
    signature: str

    def __post_init__(self):
        if self.role not in ROLES or type(self.round_number) is not int or self.round_number not in (1,2,3):
            raise PromotionError("three distinct wisdom comprehension passes required")
        if (type(self.task_digests) is not tuple or not self.task_digests or
                len(self.task_digests)>32 or
                tuple(sorted(set(self.task_digests)))!=self.task_digests):
            raise PromotionError("complete unique comprehension task coverage")
        for digest in (*self.task_digests,self.research_packet_digest,
                       self.first_weight_audit_digest,self.proofread_output_digest,
                       self.signature):
            _sha(digest,"second-glance reviewer evidence")
        if (type(self.proofread_checks) is not tuple
                or self.proofread_checks!=(
                    "evidence_trace","legal_source_scope","logical_consistency",
                    "measurement_limitations","originality","test_leakage")
                or type(self.adversarial_objection_count) is not int
                or not 0<=self.adversarial_objection_count<=1000
                or type(self.unresolved_source_conflicts) is not int
                or not 0<=self.unresolved_source_conflicts<=1000
                or type(self.quality_bp) is not int
                or not 0<=self.quality_bp<=10000):
            raise PromotionError("six exact proofreading controls and complete objection inventory required")
        _id(self.reviewer_id,"credentialed wisdom actor")
        _date(self.reviewed_at)

    def body(self):
        return dict(
            schema="skeleton.game_builder.second_wisdom_pass_attestation.v1",
            role=self.role,round_number=self.round_number,
            task_digests=list(self.task_digests),
            research_packet_digest=self.research_packet_digest,
            first_weight_audit_digest=self.first_weight_audit_digest,
            proofread_output_digest=self.proofread_output_digest,
            proofread_checks=list(self.proofread_checks),
            adversarial_objection_count=self.adversarial_objection_count,
            unresolved_source_conflicts=self.unresolved_source_conflicts,
            quality_bp=self.quality_bp,reviewer_id=self.reviewer_id,
            reviewed_at=self.reviewed_at)

    def payload(self):
        return dict(self.body(),signature=self.signature)


def sign_wisdom_pass(row: WisdomPassAttestation,
                     reviewer: TrustedCompetitionJudge):
    if (not isinstance(row,WisdomPassAttestation)
            or not isinstance(reviewer,TrustedCompetitionJudge)
            or reviewer.judge_id!=row.reviewer_id):
        raise PromotionError("wisdom reports must come from one exact configured actor")
    return replace(row,signature=_mac(row.body(),reviewer.key))


@dataclass(frozen=True,slots=True)
class SecondaryWisdomCycle:
    original_post_weight_digest: str
    original_knowledge_digest: str
    digested_knowledge_digest: str
    native_research_fingerprint: str
    tasks: tuple[DigestionTask,...]
    verification_receipts: tuple[str,...]
    source_breadth_increased: bool
    comprehension_cleared: bool
    new_train_worlds_independent: bool
    second_training: IntegratedLearningCycle|None
    post_second_weights: PostWeightReport|None
    blockers: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.second_glance_knowledge_and_weights.v1",
            original_post_weight_digest=self.original_post_weight_digest,
            original_knowledge_digest=self.original_knowledge_digest,
            digested_knowledge_digest=self.digested_knowledge_digest,
            native_research_fingerprint=self.native_research_fingerprint,
            tasks=[task.payload() for task in self.tasks],
            verification_receipts=list(self.verification_receipts),
            source_breadth_increased=self.source_breadth_increased,
            comprehension_cleared=self.comprehension_cleared,
            new_train_worlds_independent=self.new_train_worlds_independent,
            second_training=self.second_training.payload()
                if self.second_training else None,
            post_second_weights=self.post_second_weights.payload()
                if self.post_second_weights else None,
            blockers=list(self.blockers),
            real_second_reviewer_sgd_executed=(
                self.second_training is not None and
                self.second_training.optimization is not None),
            protected_first_holdout_reused_for_training=False,
            speculative_crawler_requests_treated_as_papers=False,
            reference_only_sources_never_in_gradients=True,
            foundation_llm_weights_updated=False,
            secondary_model_staged_or_activated=False)


def _full_tasks(first: DragonWisdomAlmanac,
                second: DragonWisdomAlmanac,
                mission: PostWeightDragonMission)->tuple[DigestionTask,...]:
    tasks=[]
    for round_number,(name,challenge,attack) in enumerate(ANGLES,1):
        for lens in second.lenses:
            if lens["conflict"] or lens["uncertain_groups"]:
                disproof=("Resolve disputed evidence before recommending any gradient. "+
                          attack)
            else:
                disproof=attack
            tasks.append(DigestionTask(
                round_number,lens["mechanic"],name,
                first.digest,second.digest,mission.native_mission.fingerprint,
                challenge,disproof))
    return tuple(tasks)


def run_secondary_wisdom_cycle(
    *,
    first_almanac: DragonWisdomAlmanac,
    first_post_weight: PostWeightReport,
    prior_original_games: FlowPlan,
    previous_candidate_policy: dict,
    mission: PostWeightDragonMission,
    wiki: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    rights: RightsLedger,
    media: tuple[SourceMediaReceipt,...],
    reviews: tuple[WisdomPassAttestation,...],
    reviewer_keys: tuple[tuple[str,TrustedCompetitionJudge],...],
    second_original_games: FlowPlan|None,
    authorized: bool,
    standard: PromotionStandard=PromotionStandard(),
    schedule: OptimizerSchedule=OptimizerSchedule(),
    minimum_quality_bp: int=8500,
)->SecondaryWisdomCycle:
    if not authorized:
        raise PermissionError("second-glance AI weight experimentation requires operator authority")
    if (not isinstance(first_almanac,DragonWisdomAlmanac)
            or not isinstance(first_post_weight,PostWeightReport)
            or not isinstance(prior_original_games,FlowPlan)
            or not isinstance(mission,PostWeightDragonMission)
            or not isinstance(standard,PromotionStandard)
            or not isinstance(schedule,OptimizerSchedule)
            or type(minimum_quality_bp) is not int
            or not 8000<=minimum_quality_bp<=9900):
        raise PromotionError("verified first weight report and frozen original-game source plan required")
    if (first_post_weight.plan_digest!=canonical_digest(prior_original_games.payload())
            or first_post_weight.model_after_digest!=canonical_digest(previous_candidate_policy)
            or mission.source_report_digest!=first_post_weight.digest
            or mission.previous_wisdom_digest!=first_almanac.digest
            or mission.actual_fetches!=0):
        raise PromotionError("changed weight reference or invented crawler research")
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    second=distill_dragon_peer_wisdom(
        wiki,brief,packet,rights,media,authorized=True)
    if (second.owner!=first_almanac.owner
            or second.project_id!=first_almanac.project_id):
        raise PromotionError("secondary knowledge must belong to the same original title")
    first_ids={s["source_id"] for s in first_almanac.sources}
    newer={s["source_id"] for s in second.sources}
    new_sources=[s for s in second.sources if s["source_id"] not in first_ids]
    new_groups=set().union(*(set(s["dependence_groups"])
                             for s in new_sources)) if new_sources else set()
    previous_groups=set().union(*(set(s["dependence_groups"])
                                for s in first_almanac.sources))
    if (not first_ids.issubset(newer)
            or len(new_sources)<2
            or len(new_groups-previous_groups)<2
            or second.knowledge_root==first_almanac.knowledge_root
            or second.clearance_digest==first_almanac.clearance_digest):
        raise PromotionError("second glance needs genuinely new reviewed sources and independent peer groups")
    for source in first_almanac.sources:
        record=rights.source(source["source_id"])
        if (record.rights_binding_digest!=source["rights_binding_digest"]
                or record.rights_state in {RightsState.UNKNOWN_QUARANTINE,RightsState.FORBIDDEN}
                or UseKind.FACTS_IDEAS_REFERENCE not in record.allowed_uses):
            raise PromotionError("previous source rights changed; redo first digestion and approvals")
    tasks=_full_tasks(first_almanac,second,mission)
    if (not tasks or len({t.digest for t in tasks})!=len(tasks)
            or type(reviews) is not tuple or len(reviews)!=9
            or type(reviewer_keys) is not tuple or len(reviewer_keys)!=3
            or {r for r,_ in reviewer_keys}!=set(ROLES)
            or len({s.judge_id for _,s in reviewer_keys})!=3):
        raise PromotionError("all three agents must proofread each of three complete comprehension passes")
    keyring=dict(reviewer_keys)
    groupings={r:tuple(sorted(
        t.digest for t in tasks if t.round_number==r)) for r in (1,2,3)}
    if {(x.role,x.round_number) for x in reviews}!={
            (actor,r) for actor in ROLES for r in (1,2,3)}:
        raise PromotionError("nine distinct complete second-glance actor/round reviews required")
    source_packet_digest=packet.to_payload()["packet_digest"]
    blockers=[]
    for row in reviews:
        if not isinstance(row,WisdomPassAttestation):
            raise PromotionError("typed honest second-glance review necessary")
        signer=keyring[row.role]
        if (row.reviewer_id!=signer.judge_id
                or row.research_packet_digest!=source_packet_digest
                or row.first_weight_audit_digest!=first_post_weight.digest
                or row.task_digests!=groupings[row.round_number]
                or not hmac.compare_digest(
                    row.signature,_mac(row.body(),signer.key))):
            raise PromotionError("forged, stale, cross-role or partial comprehension evidence")
        if row.quality_bp<minimum_quality_bp:
            blockers.append(row.role+":"+str(row.round_number)+":low_comprehension")
        if row.unresolved_source_conflicts:
            blockers.append(row.role+":"+str(row.round_number)+":unresolved_evidence")
        if row.adversarial_objection_count:
            blockers.append(row.role+":"+str(row.round_number)+":uncleared_adversarial_objection")
    if not first_post_weight.shadow_fit_qualified:
        blockers.append("first_weight_candidate_not_independently_qualified")
    # New originally authored projects must be independent from every
    # previous train, validation AND test game. No sealed TEST source may
    # be recycled as 'fresh' training or used to select a new checkpoint.
    independent=False
    if second_original_games is not None:
        if not isinstance(second_original_games,FlowPlan):
            raise PromotionError("new original games must pass existing split and custody planner")
        independent=not (set(prior_original_games.source_projects)
                         &set(second_original_games.source_projects))
        if not independent:
            raise PromotionError("first protected TRAIN/VAL/TEST worlds reused as second-gradient evidence")
    else:
        blockers.append("new_original_train_validation_test_worlds_not_present")
    learning=None
    after=None
    if independent and not blockers:
        learning=run_integrated_learning_cycle(
            wiki,brief,packet,rights,media,second_original_games,
            authorized=True,standard=standard,schedule=schedule,
            champion=previous_candidate_policy)
        if learning.optimization is None:
            blockers.extend(x["reason"] for x in learning.gaps)
        else:
            after=analyze_post_weight_change(
                second_original_games,learning.optimization,
                standard=standard,champion=previous_candidate_policy,
                authorized=True)
            if not after.shadow_fit_qualified:
                blockers.extend(after.safety_objections or (
                    "second_weight_candidate_failed_independent_evaluation",))
    return SecondaryWisdomCycle(
        first_post_weight.digest,first_almanac.digest,second.digest,
        mission.native_mission.fingerprint,tasks,
        tuple(sorted(canonical_digest(x.payload()) for x in reviews)),
        True,not any("comprehension" in x or "evidence" in x
                     or "objection" in x for x in blockers),
        independent,learning,after,tuple(sorted(set(blockers))))


__all__=["ROLES","ANGLES","DigestionTask","WisdomPassAttestation",
         "sign_wisdom_pass","SecondaryWisdomCycle","run_secondary_wisdom_cycle"]
