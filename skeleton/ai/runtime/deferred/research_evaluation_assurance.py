"""Assurance bindings for the deferred research/evaluation plane, VOL-210..VOL-220.

The older research_evaluation module provides bounded primitives.  This module
adds the governance seams required by the masterplan: role templates and
verification-standard binding, literature triage to backlog, citation analytics,
reproduction-package identity, comparison eligibility, approved statistical
plans, model/agent evaluation acceptance evidence, bounded long-horizon runs,
contamination fingerprint evidence, and blinded human-evaluation bindings.

All results are evidence-only and grant no production or promotion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import statistics
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json
from .research_evaluation import (
    CitationEdge,
    CitationGraph,
    ContaminationAuditor,
    EvalCase,
    EvalOutcome,
    EvaluationHarness,
    ExperimentComparator,
    ExperimentRun,
    HumanEvaluation,
    HumanJudgment,
    LiteratureItem,
    LiteratureWatch,
    ReproductionBundle,
    ResearchRole,
    ResearchTeam,
    Sample,
    StatisticalAnalyzer,
)


class ResearchEvaluationAssuranceError(ValueError):
    pass


_HEX=frozenset("0123456789abcdef")


def _text(name:str,value:object,*,limit:int=512)->str:
    if (
        not isinstance(value,str)
        or not value
        or value!=value.strip()
        or len(value)>limit
        or any(ord(ch)<32 for ch in value)
    ):
        raise ResearchEvaluationAssuranceError(
            f"{name} must be normalized non-empty text"
        )
    return value


def _texts(name:str,values:Iterable[str],*,allow_empty:bool=False)->tuple[str,...]:
    if isinstance(values,(str,bytes)):
        raise ResearchEvaluationAssuranceError(f"{name} must be a collection")
    result=tuple(sorted({_text(name,value) for value in values}))
    if not result and not allow_empty:
        raise ResearchEvaluationAssuranceError(f"{name} must be non-empty")
    return result


def _integer(name:str,value:object,*,minimum:int=0)->int:
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
        raise ResearchEvaluationAssuranceError(
            f"{name} must be an integer >= {minimum}"
        )
    return value


def _finite(name:str,value:object)->float:
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ResearchEvaluationAssuranceError(f"{name} must be numeric")
    result=float(value)
    if not math.isfinite(result):
        raise ResearchEvaluationAssuranceError(f"{name} must be finite")
    return result


def _unit(name:str,value:object)->float:
    result=_finite(name,value)
    if not 0.0<=result<=1.0:
        raise ResearchEvaluationAssuranceError(f"{name} must be within [0, 1]")
    return result


def _sha(name:str,value:object,*,length:int=64)->str:
    text=_text(name,value,limit=length)
    if len(text)!=length or any(ch not in _HEX for ch in text):
        raise ResearchEvaluationAssuranceError(
            f"{name} must be lowercase {length}-character hexadecimal"
        )
    return text


# VOL-210 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ResearchRoleTemplate:
    role_id:str
    purpose:str
    independence_group:str
    allowed_actions:tuple[str,...]
    forbidden_actions:tuple[str,...]=("production_mutation","self_verification")

    def __post_init__(self)->None:
        for name in ("role_id","purpose","independence_group"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(
            self,"allowed_actions",_texts("allowed_action",self.allowed_actions)
        )
        object.__setattr__(
            self,"forbidden_actions",_texts("forbidden_action",self.forbidden_actions)
        )
        if set(self.allowed_actions)&set(self.forbidden_actions):
            raise ResearchEvaluationAssuranceError("research role action overlap")
        for required in ("production_mutation","self_verification"):
            if required not in self.forbidden_actions:
                raise ResearchEvaluationAssuranceError(
                    f"research role must forbid {required}"
                )

    def materialize(self)->ResearchRole:
        return ResearchRole(self.role_id,self.purpose,self.independence_group)

    @property
    def digest(self)->str:
        return sha256_json({
            "role_id":self.role_id,
            "purpose":self.purpose,
            "independence_group":self.independence_group,
            "allowed_actions":list(self.allowed_actions),
            "forbidden_actions":list(self.forbidden_actions),
        })


@dataclass(frozen=True,slots=True)
class ResearchTeamEvidence:
    team_id:str
    verification_standard_ref:str
    role_digests:tuple[str,...]
    independent_groups:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"team_id",_text("team_id",self.team_id))
        object.__setattr__(
            self,
            "verification_standard_ref",
            _text("verification_standard_ref",self.verification_standard_ref),
        )
        digests=tuple(sorted(_sha("role_digest",value) for value in self.role_digests))
        if not digests:
            raise ResearchEvaluationAssuranceError("team evidence requires roles")
        object.__setattr__(self,"role_digests",digests)
        object.__setattr__(
            self,"independent_groups",_texts("independent_group",self.independent_groups)
        )
        if len(self.independent_groups)<2:
            raise ResearchEvaluationAssuranceError(
                "research team needs at least two independent groups"
            )
        if self.production_authority is not False:
            raise ResearchEvaluationAssuranceError(
                "research team evidence cannot grant production authority"
            )

    @property
    def digest(self)->str:
        return sha256_json({
            "team_id":self.team_id,
            "verification_standard_ref":self.verification_standard_ref,
            "role_digests":list(self.role_digests),
            "independent_groups":list(self.independent_groups),
            "production_authority":False,
        })


def build_research_team(
    team_id:str,
    templates:Sequence[ResearchRoleTemplate],
    *,
    verification_standard_ref:str,
)->tuple[ResearchTeam,ResearchTeamEvidence]:
    if len(templates)<2:
        raise ResearchEvaluationAssuranceError("research team requires two roles")
    team=ResearchTeam(tuple(template.materialize() for template in templates))
    evidence=ResearchTeamEvidence(
        _text("team_id",team_id),
        _text("verification_standard_ref",verification_standard_ref),
        tuple(template.digest for template in templates),
        tuple(template.independence_group for template in templates),
    )
    return team,evidence


# VOL-211 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class LiteratureSourceAdapter:
    adapter_id:str
    source_kind:str
    trust_tier:str
    update_channel:str
    allowed_license_classes:tuple[str,...]

    def __post_init__(self)->None:
        for name in ("adapter_id","source_kind","update_channel"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        if self.trust_tier not in {"primary","curated","discovery"}:
            raise ResearchEvaluationAssuranceError("unsupported source trust tier")
        object.__setattr__(
            self,
            "allowed_license_classes",
            _texts("allowed_license_class",self.allowed_license_classes),
        )


@dataclass(frozen=True,slots=True)
class LiteratureTriageEvidence:
    item_digest:str
    adapter_id:str
    priority:str
    backlog_ref:str|None
    reason_codes:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"item_digest",_sha("item_digest",self.item_digest))
        object.__setattr__(self,"adapter_id",_text("adapter_id",self.adapter_id))
        if self.priority not in {"ignore","watch","review","urgent"}:
            raise ResearchEvaluationAssuranceError("unknown literature priority")
        if self.backlog_ref is not None:
            object.__setattr__(
                self,"backlog_ref",_text("backlog_ref",self.backlog_ref)
            )
        object.__setattr__(
            self,"reason_codes",_texts("reason_code",self.reason_codes)
        )
        if self.priority in {"review","urgent"} and self.backlog_ref is None:
            raise ResearchEvaluationAssuranceError(
                "reviewable literature must bind research backlog"
            )
        if self.production_authority is not False:
            raise ResearchEvaluationAssuranceError(
                "literature evidence cannot grant production authority"
            )


def triage_literature(
    watch:LiteratureWatch,
    adapter:LiteratureSourceAdapter,
    item:LiteratureItem,
    *,
    topic_match:bool,
    license_class:str,
    backlog_ref:str|None=None,
)->LiteratureTriageEvidence:
    watch.ingest(item)
    license_value=_text("license_class",license_class)
    reasons:list[str]=[]
    if item.retracted:
        priority="ignore"
        reasons.append("retracted")
    elif license_value not in set(adapter.allowed_license_classes):
        priority="ignore"
        reasons.append("license-not-approved")
    elif not topic_match:
        priority="watch" if adapter.trust_tier=="primary" else "ignore"
        reasons.append("topic-miss")
    elif adapter.trust_tier=="primary":
        priority="urgent"
        reasons.append("primary-topic-match")
    elif adapter.trust_tier=="curated":
        priority="review"
        reasons.append("curated-topic-match")
    else:
        priority="watch"
        reasons.append("discovery-topic-match")
    bound_backlog=backlog_ref if priority in {"review","urgent"} else None
    if bound_backlog is not None:
        bound_backlog=_text("backlog_ref",bound_backlog)
    return LiteratureTriageEvidence(
        sha256_json({
            "source_id":item.source_id,
            "version":item.version,
            "title":item.title,
            "source_digest":item.source_digest,
            "retracted":item.retracted,
        }),
        adapter.adapter_id,
        priority,
        bound_backlog,
        tuple(reasons),
    )


# VOL-212 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class CitationAnalyticsEvidence:
    target_id:str
    support_count:int
    independent_sources:tuple[str,...]
    contradiction_sources:tuple[str,...]
    graph_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"target_id",_text("target_id",self.target_id))
        object.__setattr__(
            self,"support_count",_integer("support_count",self.support_count)
        )
        object.__setattr__(
            self,
            "independent_sources",
            _texts("independent_source",self.independent_sources,allow_empty=True),
        )
        object.__setattr__(
            self,
            "contradiction_sources",
            _texts("contradiction_source",self.contradiction_sources,allow_empty=True),
        )
        object.__setattr__(self,"graph_digest",_sha("graph_digest",self.graph_digest))


def analyze_citation_target(
    edges:Sequence[CitationEdge],
    *,
    target_id:str,
)->CitationAnalyticsEvidence:
    target=_text("target_id",target_id)
    graph=CitationGraph()
    canonical=[]
    seen=set()
    for edge in edges:
        identity=(edge.source_id,edge.target_id,edge.relation)
        if identity in seen:
            raise ResearchEvaluationAssuranceError("duplicate citation edge")
        seen.add(identity)
        graph.add(edge)
        canonical.append(identity)
    supporting=graph.independent_sources(target)
    contradictions=tuple(sorted({
        edge.source_id
        for edge in edges
        if edge.target_id==target and edge.relation in {"contradicts","retracts"}
    }))
    return CitationAnalyticsEvidence(
        target,
        graph.support_count(target),
        supporting,
        contradictions,
        sha256_json({"edges":[list(item) for item in sorted(canonical)]}),
    )


# VOL-213 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ReproductionPackageEvidence:
    bundle_digest:str
    revision_sha:str
    artifact_digests:tuple[str,...]
    secret_free:bool=True
    external_side_effects:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"bundle_digest",_sha("bundle_digest",self.bundle_digest))
        object.__setattr__(
            self,"revision_sha",_sha("revision_sha",self.revision_sha,length=40)
        )
        values=tuple(sorted(_sha("artifact_digest",value) for value in self.artifact_digests))
        if not values:
            raise ResearchEvaluationAssuranceError(
                "reproduction package needs artifact digests"
            )
        object.__setattr__(self,"artifact_digests",values)
        if self.secret_free is not True:
            raise ResearchEvaluationAssuranceError(
                "reproduction package must be secret-free"
            )
        if self.external_side_effects is not False:
            raise ResearchEvaluationAssuranceError(
                "reproduction package cannot authorize external effects"
            )

    @property
    def digest(self)->str:
        return sha256_json({
            "bundle_digest":self.bundle_digest,
            "revision_sha":self.revision_sha,
            "artifact_digests":list(self.artifact_digests),
            "secret_free":True,
            "external_side_effects":False,
        })


def qualify_reproduction_package(
    bundle:ReproductionBundle,
    *,
    revision_sha:str,
    artifact_digests:Iterable[str],
    secret_present:bool=False,
)->ReproductionPackageEvidence:
    if secret_present is not False:
        raise ResearchEvaluationAssuranceError(
            "reproduction package cannot contain secrets"
        )
    return ReproductionPackageEvidence(
        bundle.digest,
        _sha("revision_sha",revision_sha,length=40),
        tuple(artifact_digests),
    )


# VOL-214 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ExperimentComparisonEvidence:
    baseline_id:str
    candidate_id:str
    eligible:bool
    reason_code:str
    delta:float|None
    baseline_digest:str
    candidate_digest:str

    def __post_init__(self)->None:
        for name in ("baseline_id","candidate_id","reason_code"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        if not isinstance(self.eligible,bool):
            raise ResearchEvaluationAssuranceError("eligible must be boolean")
        if self.delta is not None:
            object.__setattr__(self,"delta",_finite("delta",self.delta))
        if self.eligible!=(self.delta is not None):
            raise ResearchEvaluationAssuranceError(
                "eligible comparison must carry exactly one delta"
            )
        object.__setattr__(
            self,"baseline_digest",_sha("baseline_digest",self.baseline_digest)
        )
        object.__setattr__(
            self,"candidate_digest",_sha("candidate_digest",self.candidate_digest)
        )


def compare_experiment_runs(
    baseline:ExperimentRun,
    candidate:ExperimentRun,
    *,
    require_same_seed:bool=False,
)->ExperimentComparisonEvidence:
    reason="eligible"
    eligible=ExperimentComparator.comparable(baseline,candidate)
    if not eligible:
        reason="identity-mismatch"
    elif require_same_seed and baseline.seed!=candidate.seed:
        eligible=False
        reason="seed-mismatch"
    if eligible:
        delta=ExperimentComparator.delta(baseline,candidate)
    else:
        delta=None
    return ExperimentComparisonEvidence(
        baseline.run_id,
        candidate.run_id,
        eligible,
        reason,
        delta,
        sha256_json({
            "run_id":baseline.run_id,
            "experiment_id":baseline.experiment_id,
            "dataset_digest":baseline.dataset_digest,
            "config_digest":baseline.config_digest,
            "metric_name":baseline.metric_name,
            "metric_value":baseline.metric_value,
            "seed":baseline.seed,
        }),
        sha256_json({
            "run_id":candidate.run_id,
            "experiment_id":candidate.experiment_id,
            "dataset_digest":candidate.dataset_digest,
            "config_digest":candidate.config_digest,
            "metric_name":candidate.metric_name,
            "metric_value":candidate.metric_value,
            "seed":candidate.seed,
        }),
    )


# VOL-215 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class StatisticalAnalysisPlan:
    analysis_id:str
    method:str
    alpha:float
    minimum_samples:int
    metric_name:str

    def __post_init__(self)->None:
        for name in ("analysis_id","method","metric_name"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        if self.method not in {"descriptive","mean-difference"}:
            raise ResearchEvaluationAssuranceError(
                "statistical method is not approved"
            )
        alpha=_finite("alpha",self.alpha)
        if not 0.0<alpha<0.5:
            raise ResearchEvaluationAssuranceError("alpha must be within (0,0.5)")
        object.__setattr__(self,"alpha",alpha)
        object.__setattr__(
            self,
            "minimum_samples",
            _integer("minimum_samples",self.minimum_samples,minimum=2),
        )

    @property
    def digest(self)->str:
        return sha256_json({
            "analysis_id":self.analysis_id,
            "method":self.method,
            "alpha":self.alpha,
            "minimum_samples":self.minimum_samples,
            "metric_name":self.metric_name,
        })


@dataclass(frozen=True,slots=True)
class StatisticalAnalysisEvidence:
    plan_digest:str
    baseline_count:int
    candidate_count:int
    baseline_mean:float
    candidate_mean:float
    mean_delta:float
    sufficient_samples:bool

    def __post_init__(self)->None:
        object.__setattr__(self,"plan_digest",_sha("plan_digest",self.plan_digest))
        for name in ("baseline_count","candidate_count"):
            object.__setattr__(
                self,name,_integer(name,getattr(self,name))
            )
        for name in ("baseline_mean","candidate_mean","mean_delta"):
            object.__setattr__(
                self,name,_finite(name,getattr(self,name))
            )
        if not isinstance(self.sufficient_samples,bool):
            raise ResearchEvaluationAssuranceError(
                "sufficient_samples must be boolean"
            )


def analyze_comparison(
    plan:StatisticalAnalysisPlan,
    baseline:Sequence[Sample],
    candidate:Sequence[Sample],
)->StatisticalAnalysisEvidence:
    left=StatisticalAnalyzer.summarize(baseline)
    right=StatisticalAnalyzer.summarize(candidate)
    sufficient=(
        left.count>=plan.minimum_samples
        and right.count>=plan.minimum_samples
    )
    return StatisticalAnalysisEvidence(
        plan.digest,
        left.count,
        right.count,
        left.average,
        right.average,
        right.average-left.average,
        sufficient,
    )


# VOL-216 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ModelEvaluationPolicy:
    policy_id:str
    minimum_mean_score:float
    minimum_case_score:float
    require_clean_contamination:bool=True

    def __post_init__(self)->None:
        object.__setattr__(self,"policy_id",_text("policy_id",self.policy_id))
        object.__setattr__(
            self,"minimum_mean_score",_unit("minimum_mean_score",self.minimum_mean_score)
        )
        object.__setattr__(
            self,"minimum_case_score",_unit("minimum_case_score",self.minimum_case_score)
        )
        if not isinstance(self.require_clean_contamination,bool):
            raise ResearchEvaluationAssuranceError(
                "require_clean_contamination must be boolean"
            )


@dataclass(frozen=True,slots=True)
class ModelEvaluationEvidence:
    policy_id:str
    model_digest:str
    metrics:tuple[tuple[str,float],...]
    contamination_status:str
    passed:bool
    blockers:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"policy_id",_text("policy_id",self.policy_id))
        object.__setattr__(self,"model_digest",_sha("model_digest",self.model_digest))
        if not isinstance(self.metrics,tuple) or not self.metrics:
            raise ResearchEvaluationAssuranceError("evaluation metrics required")
        normalized=tuple(
            sorted(
                (
                    _text("metric_name",name),
                    _finite(f"metric:{name}",value),
                )
                for name,value in self.metrics
            )
        )
        object.__setattr__(self,"metrics",normalized)
        if self.contamination_status not in {"clean","suspected","confirmed","unknown"}:
            raise ResearchEvaluationAssuranceError(
                "unknown contamination status"
            )
        if not isinstance(self.passed,bool):
            raise ResearchEvaluationAssuranceError("passed must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if self.passed!=(not self.blockers):
            raise ResearchEvaluationAssuranceError(
                "model evaluation pass state must match blockers"
            )
        if self.production_authority is not False:
            raise ResearchEvaluationAssuranceError(
                "evaluation evidence cannot grant production authority"
            )


def evaluate_model(
    harness:EvaluationHarness,
    outcomes:Sequence[EvalOutcome],
    *,
    model_digest:str,
    policy:ModelEvaluationPolicy,
    contamination_status:str,
)->ModelEvaluationEvidence:
    metrics=harness.evaluate(outcomes)
    blockers=[]
    if metrics["mean_score"]<policy.minimum_mean_score:
        blockers.append("mean-score-below-policy")
    if metrics["minimum_score"]<policy.minimum_case_score:
        blockers.append("minimum-case-score-below-policy")
    if policy.require_clean_contamination and contamination_status!="clean":
        blockers.append("contamination-not-clean")
    return ModelEvaluationEvidence(
        policy.policy_id,
        _sha("model_digest",model_digest),
        tuple(metrics.items()),
        contamination_status,
        not blockers,
        tuple(sorted(blockers)),
    )


# VOL-217 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class AgentEvaluationEvidence:
    agent_digest:str
    metrics:tuple[tuple[str,float],...]
    trajectory_coverage:float
    blockers:tuple[str,...]
    passed:bool
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"agent_digest",_sha("agent_digest",self.agent_digest))
        if not self.metrics:
            raise ResearchEvaluationAssuranceError("agent metrics required")
        object.__setattr__(
            self,
            "metrics",
            tuple(sorted((_text("metric",k),_finite(f"metric:{k}",v)) for k,v in self.metrics)),
        )
        object.__setattr__(
            self,
            "trajectory_coverage",
            _unit("trajectory_coverage",self.trajectory_coverage),
        )
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if not isinstance(self.passed,bool):
            raise ResearchEvaluationAssuranceError("passed must be boolean")
        if self.passed!=(not self.blockers):
            raise ResearchEvaluationAssuranceError(
                "agent evaluation pass state must match blockers"
            )
        if self.production_authority is not False:
            raise ResearchEvaluationAssuranceError(
                "agent evaluation cannot grant production authority"
            )


def evaluate_agent(
    harness:EvaluationHarness,
    outcomes:Sequence[EvalOutcome],
    *,
    agent_digest:str,
    minimum_score:float,
)->AgentEvaluationEvidence:
    metrics=harness.evaluate(outcomes)
    threshold=_unit("minimum_score",minimum_score)
    trajectory_count=sum(1 for item in outcomes if item.trajectory_digest is not None)
    coverage=trajectory_count/len(outcomes)
    blockers=[]
    if metrics["mean_score"]<threshold:
        blockers.append("mean-score-below-policy")
    if coverage<1.0:
        blockers.append("trajectory-evidence-incomplete")
    return AgentEvaluationEvidence(
        _sha("agent_digest",agent_digest),
        tuple(metrics.items()),
        coverage,
        tuple(sorted(blockers)),
        not blockers,
    )


# VOL-218 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class LongHorizonCheckpoint:
    step:int
    state_digest:str
    authority_digest:str
    objective_progress:float
    recovered:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"step",_integer("step",self.step,minimum=1))
        object.__setattr__(self,"state_digest",_sha("state_digest",self.state_digest))
        object.__setattr__(
            self,"authority_digest",_sha("authority_digest",self.authority_digest)
        )
        object.__setattr__(
            self,
            "objective_progress",
            _unit("objective_progress",self.objective_progress),
        )
        if not isinstance(self.recovered,bool):
            raise ResearchEvaluationAssuranceError("recovered must be boolean")


@dataclass(frozen=True,slots=True)
class LongHorizonEvidence:
    benchmark_id:str
    max_steps:int
    checkpoint_count:int
    completed:bool
    authority_stable:bool
    progress_monotonic:bool
    recovery_count:int
    acceptance_eligible:bool

    def __post_init__(self)->None:
        object.__setattr__(self,"benchmark_id",_text("benchmark_id",self.benchmark_id))
        object.__setattr__(self,"max_steps",_integer("max_steps",self.max_steps,minimum=1))
        object.__setattr__(
            self,"checkpoint_count",_integer("checkpoint_count",self.checkpoint_count,minimum=1)
        )
        object.__setattr__(
            self,"recovery_count",_integer("recovery_count",self.recovery_count)
        )
        for name in ("completed","authority_stable","progress_monotonic","acceptance_eligible"):
            if not isinstance(getattr(self,name),bool):
                raise ResearchEvaluationAssuranceError(f"{name} must be boolean")
        expected=self.completed and self.authority_stable and self.progress_monotonic
        if self.acceptance_eligible!=expected:
            raise ResearchEvaluationAssuranceError(
                "long-horizon eligibility must match evidence"
            )


def assess_long_horizon(
    benchmark_id:str,
    *,
    max_steps:int,
    checkpoints:Sequence[LongHorizonCheckpoint],
    completed:bool,
)->LongHorizonEvidence:
    maximum=_integer("max_steps",max_steps,minimum=1)
    if not checkpoints:
        raise ResearchEvaluationAssuranceError(
            "long-horizon benchmark needs checkpoints"
        )
    steps=[item.step for item in checkpoints]
    if steps!=sorted(steps) or len(steps)!=len(set(steps)):
        raise ResearchEvaluationAssuranceError(
            "long-horizon checkpoint steps must be ordered and unique"
        )
    if steps[-1]>maximum:
        raise ResearchEvaluationAssuranceError(
            "long-horizon checkpoint exceeds step budget"
        )
    authority_stable=len({item.authority_digest for item in checkpoints})==1
    progress=[item.objective_progress for item in checkpoints]
    monotonic=all(right>=left for left,right in zip(progress,progress[1:]))
    complete=bool(completed)
    return LongHorizonEvidence(
        _text("benchmark_id",benchmark_id),
        maximum,
        len(checkpoints),
        complete,
        authority_stable,
        monotonic,
        sum(1 for item in checkpoints if item.recovered),
        complete and authority_stable and monotonic,
    )


# VOL-219 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ContaminationAuditEvidence:
    audit_id:str
    exact_overlaps:tuple[str,...]
    approximate_overlap_count:int
    status:str
    audit_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"audit_id",_text("audit_id",self.audit_id))
        object.__setattr__(
            self,
            "exact_overlaps",
            tuple(sorted(_sha("overlap_digest",value) for value in self.exact_overlaps)),
        )
        object.__setattr__(
            self,
            "approximate_overlap_count",
            _integer("approximate_overlap_count",self.approximate_overlap_count),
        )
        if self.status not in {"clean","suspected","confirmed"}:
            raise ResearchEvaluationAssuranceError(
                "unknown contamination audit status"
            )
        expected=(
            "confirmed" if self.exact_overlaps
            else "suspected" if self.approximate_overlap_count
            else "clean"
        )
        if self.status!=expected:
            raise ResearchEvaluationAssuranceError(
                "contamination status does not match evidence"
            )
        object.__setattr__(self,"audit_digest",_sha("audit_digest",self.audit_digest))


def audit_contamination(
    audit_id:str,
    *,
    train_digests:Iterable[str],
    eval_digests:Iterable[str],
    approximate_overlap_count:int=0,
)->ContaminationAuditEvidence:
    train=tuple(_sha("train_digest",value) for value in train_digests)
    evaluate=tuple(_sha("eval_digest",value) for value in eval_digests)
    overlaps=ContaminationAuditor.overlaps(train,evaluate)
    approximate=_integer("approximate_overlap_count",approximate_overlap_count)
    status="confirmed" if overlaps else "suspected" if approximate else "clean"
    digest=sha256_json({
        "audit_id":_text("audit_id",audit_id),
        "train_digests":sorted(train),
        "eval_digests":sorted(evaluate),
        "exact_overlaps":list(overlaps),
        "approximate_overlap_count":approximate,
        "status":status,
    })
    return ContaminationAuditEvidence(
        _text("audit_id",audit_id),
        overlaps,
        approximate,
        status,
        digest,
    )


def fingerprint_text(value:str)->str:
    normalized=" ".join(_text("fingerprint_text",value,limit=100_000).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# VOL-220 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class HumanRubric:
    rubric_id:str
    rubric_version:str
    minimum_raters:int
    minimum_score:float
    blinding_required:bool=True

    def __post_init__(self)->None:
        for name in ("rubric_id","rubric_version"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(
            self,
            "minimum_raters",
            _integer("minimum_raters",self.minimum_raters,minimum=1),
        )
        object.__setattr__(
            self,"minimum_score",_unit("minimum_score",self.minimum_score)
        )
        if self.blinding_required is not True:
            raise ResearchEvaluationAssuranceError(
                "human evaluation must require blinding"
            )


@dataclass(frozen=True,slots=True)
class BlindedHumanJudgment:
    judgment:HumanJudgment
    blinded:bool

    def __post_init__(self)->None:
        if not isinstance(self.judgment,HumanJudgment):
            raise ResearchEvaluationAssuranceError(
                "judgment must be HumanJudgment"
            )
        if self.blinded is not True:
            raise ResearchEvaluationAssuranceError(
                "human judgment must be blinded"
            )


@dataclass(frozen=True,slots=True)
class HumanEvaluationEvidence:
    rubric_id:str
    case_scores:tuple[tuple[str,float],...]
    passed:bool
    blockers:tuple[str,...]
    quality_vector_eligible:bool
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"rubric_id",_text("rubric_id",self.rubric_id))
        if not self.case_scores:
            raise ResearchEvaluationAssuranceError("human scores required")
        object.__setattr__(
            self,
            "case_scores",
            tuple(sorted((_text("case_id",k),_unit(f"score:{k}",v)) for k,v in self.case_scores)),
        )
        if not isinstance(self.passed,bool):
            raise ResearchEvaluationAssuranceError("passed must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if self.passed!=(not self.blockers):
            raise ResearchEvaluationAssuranceError(
                "human evaluation pass state must match blockers"
            )
        if not isinstance(self.quality_vector_eligible,bool):
            raise ResearchEvaluationAssuranceError(
                "quality_vector_eligible must be boolean"
            )
        if self.quality_vector_eligible!=self.passed:
            raise ResearchEvaluationAssuranceError(
                "human evidence is quality-vector eligible iff it passes"
            )
        if self.production_authority is not False:
            raise ResearchEvaluationAssuranceError(
                "human evaluation cannot grant production authority"
            )


def aggregate_human_evaluation(
    rubric:HumanRubric,
    judgments:Sequence[BlindedHumanJudgment],
)->HumanEvaluationEvidence:
    if not judgments:
        raise ResearchEvaluationAssuranceError(
            "human evaluation requires judgments"
        )
    raw=[item.judgment for item in judgments]
    if any(item.rubric_version!=rubric.rubric_version for item in raw):
        raise ResearchEvaluationAssuranceError(
            "human judgment rubric version drift"
        )
    scores=HumanEvaluation.aggregate(raw,min_raters=rubric.minimum_raters)
    blockers=[
        f"{case_id}:below-rubric"
        for case_id,value in scores.items()
        if value<rubric.minimum_score
    ]
    return HumanEvaluationEvidence(
        rubric.rubric_id,
        tuple(scores.items()),
        not blockers,
        tuple(sorted(blockers)),
        not blockers,
    )


__all__=[
    "AgentEvaluationEvidence",
    "BlindedHumanJudgment",
    "CitationAnalyticsEvidence",
    "ContaminationAuditEvidence",
    "ExperimentComparisonEvidence",
    "HumanEvaluationEvidence",
    "HumanRubric",
    "LiteratureSourceAdapter",
    "LiteratureTriageEvidence",
    "LongHorizonCheckpoint",
    "LongHorizonEvidence",
    "ModelEvaluationEvidence",
    "ModelEvaluationPolicy",
    "ReproductionPackageEvidence",
    "ResearchEvaluationAssuranceError",
    "ResearchRoleTemplate",
    "ResearchTeamEvidence",
    "StatisticalAnalysisEvidence",
    "StatisticalAnalysisPlan",
    "aggregate_human_evaluation",
    "analyze_citation_target",
    "analyze_comparison",
    "assess_long_horizon",
    "audit_contamination",
    "build_research_team",
    "compare_experiment_runs",
    "evaluate_agent",
    "evaluate_model",
    "fingerprint_text",
    "qualify_reproduction_package",
    "triage_literature",
]
