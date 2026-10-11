"""Evidence-based promotion quality ladder for the local game-review model.

This is an actual input-feature classifier from game_training_flow, not an LLM.
No model is promoted by a favorable training metric alone. Verification uses
frozen validation and never-trained heldout game projects, exact predictions,
per-project and attack-family breakdowns, uncertainty, regression checks,
and immutable model/source digests. It is advisory only: canonical gameplay
verification remains authoritative on every game.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from hashlib import sha256
import math

from .contracts import canonical_digest
from .competitive_mirror_training import TrainingCandidate,split_project
from .game_training_flow import (
    FlowPlan,TrainingFlowError,_features,_label,_sigmoid,
)

class PromotionError(ValueError):
    """An original game reviewer candidate has insufficient reliable evidence."""


@dataclass(frozen=True,slots=True)
class PromotionStandard:
    name: str = "game_review_progressive_2026_10_v1"
    min_train_projects: int = 2
    min_validation_projects: int = 1
    min_test_projects: int = 1
    min_per_class: int = 8
    min_balanced_accuracy: float = 0.94
    min_project_accuracy: float = 0.85
    min_critical_recall: float = 1.0
    min_wilson_recall: float = 0.72
    max_brier: float = 0.12
    max_generalization_drop: float = 0.06
    max_regression: float = 0.0
    min_family_cases: int = 2

    def __post_init__(self):
        for k in ("min_train_projects","min_validation_projects",
                  "min_test_projects","min_per_class","min_family_cases"):
            value=getattr(self,k)
            if type(value) is not int or not 1<=value<=500:
                raise PromotionError("standards need positive bounded independent evidence")
        for k in ("min_balanced_accuracy","min_project_accuracy",
                  "min_critical_recall","min_wilson_recall",
                  "max_brier","max_generalization_drop","max_regression"):
            value=getattr(self,k)
            if type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=1:
                raise PromotionError("promotion thresholds must be finite percentages")

    def payload(self):
        return dict(schema="skeleton.game_builder.reviewer_standard.v1",
                    **{key:getattr(self,key) for key in self.__dataclass_fields__})

    @property
    def digest(self):
        return canonical_digest(self.payload())


def _wilson(wins,total):
    if not total:
        return 0.0
    z=1.96
    p=wins/total
    divisor=1+z*z/total
    center=p+z*z/(2*total)
    distance=z*math.sqrt((p*(1-p)+z*z/(4*total))/total)
    return max(0.0,(center-distance)/divisor)


def validate_policy(policy: dict):
    if type(policy) is not dict or set(policy)!={
        "weights","bias","threshold","feature_spec"
    }:
        raise PromotionError("only exact typed local review ranker weights allowed")
    if policy["feature_spec"]!="input_only_key_family_hash_128_v1":
        raise PromotionError("uninstalled AI model inference adapter")
    weights=policy["weights"]
    if (type(weights) is not list or len(weights)!=128
            or any(type(w) not in (int,float) or not math.isfinite(w) or abs(w)>8.1
                   for w in weights)):
        raise PromotionError("unsupported, nonfinite or uncontrolled model weights")
    for key,lo,hi in (("bias",-30,30),("threshold",0.01,0.99)):
        value=policy[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
            raise PromotionError("invalid model calibration or threshold")
    return policy


def predict_review(case: TrainingCandidate,policy: dict):
    validate_policy(policy)
    if not isinstance(case,TrainingCandidate):
        raise PromotionError("typed source-grounded candidate required")
    raw=policy["bias"]+sum(policy["weights"][i]*v
                           for i,v in _features(case).items())
    probability=_sigmoid(raw)
    return dict(probability=round(probability,8),
                predicted_reject=probability>=policy["threshold"],
                source_example_id=case.example_id,
                advisory_only=True,
                does_not_override_canonical_gameplay_validator=True)


def _examples(plan: FlowPlan,split: str):
    if not isinstance(plan,FlowPlan):
        raise PromotionError("exact original-game dataset plan required")
    if split not in {"train","validation","test"}:
        raise PromotionError("training split must be explicit")
    result=tuple(x for x in plan.selected if x.split==split)
    if any(x.project_digest not in plan.source_projects or
           x.split!=split_project(x.project_digest) for x in result):
        raise PromotionError("untrusted split membership")
    return result


def _metric(rows: tuple[TrainingCandidate,...],policy):
    if not rows:
        return dict(n=0,tp=0,tn=0,fp=0,fn=0,balanced_accuracy=0.0,
                    accuracy=0.0,brier=1.0,critical_recall=0.0,
                    wilson_recall=0.0,attacks={},projects={})
    tp=tn=fp=fn=critical_good=critical_total=0
    squared=0.0
    attacks=defaultdict(lambda: [0,0,0])
    projects=defaultdict(lambda: [0,0,0])
    for x in rows:
        label=_label(x)
        prediction=predict_review(x,policy)
        got=int(prediction["predicted_reject"])
        p=prediction["probability"]
        correct=got==label
        family=x.input.get("attack_family","verified_control")
        if not isinstance(family,str) or len(family)>96:
            raise PromotionError("original attack family label is not bounded")
        attacks[family][0]+=1
        attacks[family][1]+=int(correct)
        attacks[family][2]+=int(label and not got)
        projects[x.project_digest][0]+=1
        projects[x.project_digest][1]+=int(correct)
        projects[x.project_digest][2]+=int(label and not got)
        if label and got:tp+=1
        elif label and not got:fn+=1
        elif not label and got:fp+=1
        else:tn+=1
        severity=x.evidence.get("severity",2)
        if type(severity) is not int or not 0<=severity<=10:
            raise PromotionError("critical severity must come from bounded game evidence")
        if label and severity>=8:
            critical_total+=1
            critical_good+=int(got)
        squared+=(p-label)**2
    n=len(rows)
    recall=tp/(tp+fn) if tp+fn else 0.0
    specificity=tn/(tn+fp) if tn+fp else 0.0
    return dict(n=n,tp=tp,tn=tn,fp=fp,fn=fn,
                balanced_accuracy=round((recall+specificity)/2,6),
                accuracy=round((tp+tn)/n,6),brier=round(squared/n,8),
                critical_recall=round(critical_good/critical_total,6)
                    if critical_total else None,
                critical_cases=critical_total,
                wilson_recall=round(_wilson(tp,tp+fn),6),
                attacks={k:dict(n=v[0],correct=v[1],missed_dangers=v[2])
                         for k,v in sorted(attacks.items())},
                projects={k:dict(n=v[0],correct=v[1],missed_dangers=v[2])
                          for k,v in sorted(projects.items())})


@dataclass(frozen=True,slots=True)
class PromotionEvaluation:
    candidate_digest: str
    dataset_digest: str
    standard_digest: str
    metrics: dict
    blockers: tuple[str,...]
    champion_digest: str | None
    evidence_digest: str

    @property
    def passed(self):
        return not self.blockers

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.model_promotion_evaluation.v1",
                    candidate_digest=self.candidate_digest,
                    dataset_digest=self.dataset_digest,
                    standard_digest=self.standard_digest,
                    metrics=self.metrics,blockers=list(self.blockers),
                    champion_digest=self.champion_digest,
                    evidence_digest=self.evidence_digest,
                    passed=self.passed,source_only_advisory=True,
                    core_llm_weights_changed=False)


def evaluate_candidate(plan: FlowPlan,fit: dict,*,
                       standard: PromotionStandard=PromotionStandard(),
                       champion: dict | None=None,
                       authorized: bool)->PromotionEvaluation:
    if not authorized:
        raise PermissionError("local game-reviewer promotion requires trusted operator")
    if not isinstance(plan,FlowPlan) or not isinstance(standard,PromotionStandard):
        raise PromotionError("typed source plan and standards required")
    if (type(fit) is not dict or fit.get("status")!="experimental_fit_only"
            or fit.get("source_plan")!=plan.run_id
            or fit.get("training_performed") is not True):
        raise PromotionError("real isolated training evidence missing for this source plan")
    policy=validate_policy(fit.get("symbolic_policy"))
    candidate_digest=canonical_digest(policy)
    if fit.get("fitted_policy_digest")!=candidate_digest:
        raise PromotionError("trained policy changed after verified source fit")
    if champion is not None:
        validate_policy(champion)
    grouped={s:_examples(plan,s) for s in ("train","validation","test")}
    metrics={s:_metric(grouped[s],policy) for s in grouped}
    blockers=[]
    projects=dict(plan.split_projects)
    for split,minimum in (
        ("train",standard.min_train_projects),
        ("validation",standard.min_validation_projects),
        ("test",standard.min_test_projects),
    ):
        if len(projects.get(split,()))<minimum:
            blockers.append(f"{split}:insufficient_independent_projects")
        if len({x.project_digest for x in grouped[split]})!=len(projects.get(split,())):
            blockers.append(f"{split}:unrepresented_project")
    # Input and replay evidence from one real original project must never
    # be in both learning and held-out evaluation sets.
    seen={}
    for split,rows in grouped.items():
        for row in rows:
            if row.example_id in seen:
                blockers.append("duplicate_example_id_across_cohorts")
            seen[row.example_id]=split
    for split in ("validation","test"):
        m=metrics[split]
        if min(m["tp"]+m["fn"],m["tn"]+m["fp"])<standard.min_per_class:
            blockers.append(f"{split}:insufficient_each_class")
        if m["balanced_accuracy"]<standard.min_balanced_accuracy:
            blockers.append(f"{split}:balanced_accuracy")
        if m["wilson_recall"]<standard.min_wilson_recall:
            blockers.append(f"{split}:uncertain_danger_recall")
        if m["critical_recall"] is None or m["critical_recall"]<standard.min_critical_recall:
            blockers.append(f"{split}:high_severity_recall")
        if m["brier"]>standard.max_brier:
            blockers.append(f"{split}:calibration_error")
        for project,counts in m["projects"].items():
            if counts["correct"]/counts["n"]<standard.min_project_accuracy:
                blockers.append(f"{split}:game_specific_regression:{project[:12]}")
        for family,counts in m["attacks"].items():
            if family=="verified_control":
                continue
            if counts["n"]<standard.min_family_cases:
                blockers.append(f"{split}:thin_attack_family:{family}")
            if counts["missed_dangers"]:
                blockers.append(f"{split}:unhandled_attack_family:{family}")
    if (metrics["validation"]["balanced_accuracy"]-
        metrics["test"]["balanced_accuracy"]>standard.max_generalization_drop):
        blockers.append("heldout_generalization_gap")
    if champion is not None:
        leader={s:_metric(grouped[s],champion) for s in ("validation","test")}
        for split in leader:
            if metrics[split]["balanced_accuracy"]+standard.max_regression < leader[split]["balanced_accuracy"]:
                blockers.append(f"{split}:champion_quality_regression")
            for project,counts in metrics[split]["projects"].items():
                old=leader[split]["projects"][project]
                if counts["correct"]<old["correct"]:
                    blockers.append(f"{split}:champion_per_game_regression:{project[:12]}")
        metrics["champion"]={k:dict(
            balanced_accuracy=v["balanced_accuracy"],brier=v["brier"],
            critical_recall=v["critical_recall"]) for k,v in leader.items()}
    dataset_digest=canonical_digest(plan.payload())
    evidence_digest=canonical_digest({
        "plan":plan.run_id,"fit":fit,"dataset":dataset_digest,
        "standard":standard.payload(),
        "champion":canonical_digest(champion) if champion else None,
    })
    return PromotionEvaluation(candidate_digest,dataset_digest,
                               standard.digest,metrics,
                               tuple(sorted(set(blockers))),
                               canonical_digest(champion) if champion else None,
                               evidence_digest)


def evaluate_fresh_cohort(rows: tuple[TrainingCandidate,...],policy: dict,*,
                          standard: PromotionStandard,
                          source_projects: tuple[str,...],authorized: bool)->dict:
    if not authorized:
        raise PermissionError("live review feedback needs operator authority")
    validate_policy(policy)
    if (not isinstance(rows,tuple) or not 16<=len(rows)<=2048
        or any(not isinstance(x,TrainingCandidate) for x in rows)):
        raise PromotionError("complete independent reviewer observations required")
    if any(x.project_digest in source_projects for x in rows):
        raise PromotionError("live feedback is not independent of training/heldout worlds")
    if len({x.example_id for x in rows})!=len(rows):
        raise PromotionError("duplicate observed source examples")
    if len({x.project_digest for x in rows})<2:
        raise PromotionError("real deployment verification requires two fresh games")
    quality=_metric(rows,policy)
    blockers=[]
    if min(quality["tp"]+quality["fn"],quality["tn"]+quality["fp"])<standard.min_per_class:
        blockers.append("live_class_support")
    if quality["balanced_accuracy"]<standard.min_balanced_accuracy:
        blockers.append("live_balanced_accuracy")
    if quality["critical_recall"] is None or quality["critical_recall"]<standard.min_critical_recall:
        blockers.append("live_critical_recall")
    if quality["wilson_recall"]<standard.min_wilson_recall:
        blockers.append("live_recall_confidence")
    if quality["brier"]>standard.max_brier:
        blockers.append("live_probability_calibration")
    for k,v in quality["projects"].items():
        if v["correct"]/v["n"]<standard.min_project_accuracy:
            blockers.append("live_project_regression:"+k[:12])
    return dict(schema="skeleton.game_builder.fresh_cohort.v1",
                metrics=quality,blockers=sorted(set(blockers)),
                passed=not blockers,source_project_ids=sorted({
                    x.project_digest for x in rows
                }),cohort_digest=canonical_digest([x.payload() for x in rows]),
                advisory_only=True)


__all__=[
    "PromotionError","PromotionStandard","PromotionEvaluation",
    "validate_policy","predict_review","evaluate_candidate",
    "evaluate_fresh_cohort",
]
