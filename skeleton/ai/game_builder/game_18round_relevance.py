"""Round-3 evidence-weighted task relevance and historical predecessor knowledge.

A 'probability of usefulness' is a Beta-binomial *posterior heuristic*
from separately witnessed beneficial / unhelpful original project uses,
NOT a calibrated forecast of model superiority. Context applicability
and historical lineage are separately explained, never collapsed into
unsupported causal claims. Reference-only Wiki articles affect research
routing, never gradients or installed model parameters.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from math import sqrt
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError,_sha,_id
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .competitive_evolution_chain import RivalEvolutionChain
from .game_dragon_peer_wisdom import DragonWisdomAlmanac

@dataclass(frozen=True,slots=True)
class OriginalTaskFocus:
    original_id: str
    original_design_digest: str
    task_digest: str
    genre: str
    era: str
    themes: tuple[str,...]
    capabilities: tuple[str,...]
    project_priority_bp: int
    budget_mb: int

    def __post_init__(self):
        _id(self.original_id,"user original")
        for d in (self.original_design_digest,self.task_digest):_sha(d)
        for value in (self.genre,self.era):_id(value,"era or genre")
        for values in (self.themes,self.capabilities):
            if type(values) is not tuple or not values or len(values)>24 or any(
                not isinstance(v,str) or len(v)>80 or len(v)<2 for v in values):
                raise ThreatRadarError("bounded nonempty user project priorities")
        if type(self.project_priority_bp) is not int or not 0<=self.project_priority_bp<=10000:
            raise ThreatRadarError("quantized task importance required")
        if type(self.budget_mb) is not int or not 64<=self.budget_mb<=65536:
            raise ThreatRadarError("real bounded consumer hardware budget required")

    def payload(self):
        return dict(schema="skeleton.game_ai.18round_task_focus.v1",
                    original_id=self.original_id,
                    original_design_digest=self.original_design_digest,
                    task_digest=self.task_digest,genre=self.genre,era=self.era,
                    themes=list(self.themes),capabilities=list(self.capabilities),
                    project_priority_bp=self.project_priority_bp,
                    budget_mb=self.budget_mb)

@dataclass(frozen=True,slots=True)
class RelevantKnowledge:
    topic_id: str
    mechanic: str
    source_almanac_digest: str
    matching_genres: tuple[str,...]
    matching_eras: tuple[str,...]
    matching_themes: tuple[str,...]
    capabilities: tuple[str,...]
    predecessor_stage_ids: tuple[str,...]
    reference_only: bool
    memory_mb: int
    original_adapter_digest: str|None

    def __post_init__(self):
        for v in (self.topic_id,self.mechanic):_id(v,"knowledge identity")
        _sha(self.source_almanac_digest)
        for values in (self.matching_genres,self.matching_eras,self.matching_themes,
                       self.capabilities,self.predecessor_stage_ids):
            if type(values) is not tuple or len(values)>48 or len(set(values))!=len(values):
                raise ThreatRadarError("typed nonduplicate knowledge correlation axes")
            for v in values:_id(v,"task topic")
        if type(self.reference_only) is not bool or type(self.memory_mb) is not int or not 1<=self.memory_mb<=8192:
            raise ThreatRadarError("knowledge source rights and modular memory budget required")
        if self.original_adapter_digest is not None:_sha(self.original_adapter_digest)

    def payload(self):
        return dict(schema="skeleton.game_ai.knowledge_routing_subject.v1",
                    topic_id=self.topic_id,mechanic=self.mechanic,
                    source_almanac_digest=self.source_almanac_digest,
                    matching_genres=list(self.matching_genres),
                    matching_eras=list(self.matching_eras),
                    matching_themes=list(self.matching_themes),
                    capabilities=list(self.capabilities),
                    predecessor_stage_ids=list(self.predecessor_stage_ids),
                    reference_only=self.reference_only,memory_mb=self.memory_mb,
                    original_adapter_digest=self.original_adapter_digest)

@dataclass(frozen=True,slots=True)
class SignedUtilityObservation:
    topic_id: str
    original_project_digest: str
    verification_digest: str
    independence_group: str
    improved: bool
    signer_id: str
    signature: str

    def __post_init__(self):
        _id(self.topic_id,"topic")
        _id(self.independence_group,"distinct original-game group")
        _id(self.signer_id,"reviewer identity")
        _sha(self.original_project_digest);_sha(self.verification_digest);_sha(self.signature)
        if type(self.improved) is not bool:
            raise ThreatRadarError("only predeclared measured improvement boolean")

    def body(self):
        return dict(topic_id=self.topic_id,original_project_digest=self.original_project_digest,
                    verification_digest=self.verification_digest,
                    independence_group=self.independence_group,improved=self.improved,
                    signer_id=self.signer_id)

def sign_utility_observation(row:SignedUtilityObservation,judge:TrustedCompetitionJudge):
    if not isinstance(row,SignedUtilityObservation) or judge.judge_id!=row.signer_id:
        raise ThreatRadarError("no transferred utility reviewer authority")
    return replace(row,signature=_mac(row.body(),judge.key))

@dataclass(frozen=True,slots=True)
class TopicPriority:
    topic_id: str
    posterior_mean_bp: int
    conservative_utility_bp: int
    context_relevance_bp: int
    predecessor_coverage_bp: int
    estimated_usefulness_bp: int
    observations: int
    independent_projects: int
    rights: str
    mode: str
    reason_codes: tuple[str,...]
    topic_digest: str

    def payload(self):
        return dict(schema="skeleton.game_ai.task_correlated_hyperweight_priority.v1",
                    topic_id=self.topic_id,posterior_mean_bp=self.posterior_mean_bp,
                    conservative_utility_bp=self.conservative_utility_bp,
                    context_relevance_bp=self.context_relevance_bp,
                    predecessor_coverage_bp=self.predecessor_coverage_bp,
                    estimated_usefulness_bp=self.estimated_usefulness_bp,
                    observations=self.observations,independent_projects=self.independent_projects,
                    rights=self.rights,mode=self.mode,reason_codes=list(self.reason_codes),
                    topic_digest=self.topic_digest,calibrated_probability_claim=False,
                    direct_llm_weight_write=False)

def score_task_knowledge(
    task:OriginalTaskFocus,almanac:DragonWisdomAlmanac,
    subjects:tuple[RelevantKnowledge,...],observations:tuple[SignedUtilityObservation,...],
    reviewers:tuple[TrustedCompetitionJudge,...], *,
    lineage:RivalEvolutionChain|None,
    authorized:bool,
)->tuple[TopicPriority,...]:
    if not authorized:raise PermissionError("game-task research priority requires operator consent")
    if (not isinstance(task,OriginalTaskFocus) or not isinstance(almanac,DragonWisdomAlmanac)
            or type(subjects) is not tuple or not 1<=len(subjects)<=256
            or len({s.topic_id for s in subjects})!=len(subjects)
            or any(not isinstance(s,RelevantKnowledge) for s in subjects)
            or type(observations) is not tuple or len(observations)>8192
            or any(not isinstance(x,SignedUtilityObservation) for x in observations)
            or type(reviewers) is not tuple or len({x.judge_id for x in reviewers})!=len(reviewers)
            or any(not isinstance(x,TrustedCompetitionJudge) for x in reviewers)):
        raise ThreatRadarError("bounded typed source evidence and independent reviewer roster")
    if lineage is not None and not isinstance(lineage,RivalEvolutionChain):
        raise ThreatRadarError("only verified comparable game lineage")
    almanac_mechanics={x["mechanic"] for x in almanac.lenses}
    by_id={s.topic_id:s for s in subjects}
    keys={x.judge_id:x for x in reviewers}
    grouped={s.topic_id:[] for s in subjects}
    seen_groups=set()
    for row in observations:
        key=keys.get(row.signer_id)
        if (row.topic_id not in grouped or key is None or not hmac.compare_digest(
                _mac(row.body(),key.key),row.signature)):
            raise ThreatRadarError("unverified topic usefulness outcome or signer")
        unique=(row.topic_id,row.independence_group)
        if unique in seen_groups:
            raise ThreatRadarError("duplicate independent publisher/project grouping artificially raises probability")
        seen_groups.add(unique);grouped[row.topic_id].append(row)
    lineage_stages={s.title_id:s for s in lineage.stages} if lineage else {}
    out=[]
    for subject in subjects:
        if subject.mechanic not in almanac_mechanics or subject.source_almanac_digest!=almanac.digest:
            raise ThreatRadarError("topic is absent from frozen source-rights almanac")
        if set(subject.predecessor_stage_ids)-set(lineage_stages):
            raise ThreatRadarError("claimed historical comparison stage is unverified")
        rows=grouped[subject.topic_id]
        successes=sum(x.improved for x in rows)
        alpha=2+successes;beta=2+len(rows)-successes
        mean=alpha/(alpha+beta)
        std=sqrt((alpha*beta)/((alpha+beta)**2*(alpha+beta+1)))
        low=max(0.0,mean-1.645*std)
        domain_matches=[
            int(task.genre in subject.matching_genres),
            int(task.era in subject.matching_eras),
            round(len(set(task.themes)&set(subject.matching_themes))/
                  len(task.themes),3),
            round(len(set(task.capabilities)&set(subject.capabilities))/
                  len(task.capabilities),3)]
        # Explicit fixed weights, no hidden 'infinite relevance' boost.
        applicability=sum(a*b for a,b in zip(domain_matches,(0.27,0.18,0.20,0.35)))
        if lineage_stages and subject.predecessor_stage_ids:
            covered=len(subject.predecessor_stage_ids)/len(lineage_stages)
        else:covered=0.0
        relevant=min(1.0,applicability*0.85+min(covered,1.0)*0.15)
        score=int(round(10000*low*relevant))
        reasons=[]
        if len(rows)<2:reasons.append("insufficient_independent_project_outcomes")
        if subject.reference_only:reasons.append("reference_only_not_training_eligible")
        if not lineage or not lineage.complete_competitor_coverage:
            reasons.append("incomplete_predecessor_evidence")
        if not subject.original_adapter_digest:reasons.append("no_proven_original_adapter")
        mode=("experimental_shadow_candidate" if not reasons and
              subject.original_adapter_digest is not None else "research_queue_only")
        out.append(TopicPriority(
            subject.topic_id,round(10000*mean),round(10000*low),
            round(10000*applicability),round(10000*min(covered,1.0)),
            score,len(rows),len({x.original_project_digest for x in rows}),
            "reference_only" if subject.reference_only else "separately_training_licensed",
            mode,tuple(reasons),canonical_digest(subject.payload())))
    return tuple(sorted(out,key=lambda x:(-x.estimated_usefulness_bp,x.topic_id)))

__all__=["OriginalTaskFocus","RelevantKnowledge","SignedUtilityObservation",
         "sign_utility_observation","TopicPriority","score_task_knowledge"]
