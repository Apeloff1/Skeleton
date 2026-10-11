"""Second-generation original-game reviewer with normalized evidence features.

Learns from TRAIN-project adversarially equivalent envelope presentations,
not from attack-family labels or expected verdict fields. Stable nested
evidence normalization makes unusual but source-preserving JSON layouts
readable. It remains a small supervised *advisory* classifier; actual quest
facts require the canonical game simulator and independent review.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from dataclasses import replace
from hashlib import sha256
import math

from .contracts import canonical_digest
from .competitive_mirror_training import TrainingCandidate,split_project
from .game_training_flow import (
    FlowPlan,TrainingFlowError,_label,_sigmoid,
)
from .game_learning_challenges import _variants

FEATURE_SPEC="normalized_game_evidence_256_v2"
FEATURE_DIM=256
NEUTRAL_LABELS=frozenset((
    "attack_family","review_display_hint","representation","display_hint",
    "source_campaign_digest","source_project","source_world",
    "source_state","family","persona","severity",
))


def _walk(node,depth=0):
    if depth>12:
        return
    if type(node) is dict:
        for key,value in sorted(node.items()):
            if not isinstance(key,str) or len(key)>128:
                continue
            if key in {"raw_gameplay","evidence_bundle","game_event_evidence",
                       "source_payload","payload","wrapped"}:
                yield from _walk(value,depth+1)
            elif key in NEUTRAL_LABELS:
                continue
            elif key in {"canonical_witness","verified_replay","observed_event"}:
                yield "witness"
                yield from _walk(value,depth+1)
            elif key in {"before","after","mutated_fragment","original_fragment"}:
                yield "replay_fragment"
                yield from _walk(value,depth+1)
            elif key in {"changed_field","mutation_difference"}:
                yield "changed_replay"
                if isinstance(value,str):
                    yield "field:"+value[:64]
            elif key in {"event","subject","scene","origin","source_memory_digest",
                         "source_goal","verified_replay_digest","world_digest"}:
                yield "witness_fact:"+key
            elif type(value) in (dict,list,tuple):
                yield from _walk(value,depth+1)
            elif key in {"verified","observed","witnessed"} and type(value) is bool:
                yield "observed_"+str(value).lower()
    elif isinstance(node,(tuple,list)):
        for item in node[:100]:
            yield from _walk(item,depth+1)


def evidence_features(case: TrainingCandidate)->dict[int,int]:
    if not isinstance(case,TrainingCandidate) or type(case.input) is not dict:
        raise TrainingFlowError("typed original game evidence required for normalized reviewer")
    tokens=set(_walk(case.input))
    if not tokens:
        tokens.add("no_source_witness")
    if "witness" in tokens:
        tokens.discard("no_source_witness")
    # Hash semantic facts, not attack names, source IDs or split labels.
    result={}
    for token in sorted(tokens):
        slot=int.from_bytes(sha256(("v2:"+token).encode()).digest()[:4],
                            "big")%FEATURE_DIM
        result[slot]=min(4,result.get(slot,0)+1)
    return result


def _probability(case,weights,bias):
    features=evidence_features(case)
    return _sigmoid(bias+sum(weights[k]*v for k,v in features.items()))


def _score(rows,weights,bias,threshold):
    tp=tn=fp=fn=0
    brier=0.0
    for case in rows:
        y=_label(case)
        prob=_probability(case,weights,bias)
        pred=int(prob>=threshold)
        if y and pred:tp+=1
        elif y and not pred:fn+=1
        elif not y and pred:fp+=1
        else:tn+=1
        brier+=(prob-y)**2
    total=max(1,len(rows))
    return dict(n=len(rows),tp=tp,tn=tn,fp=fp,fn=fn,
                balanced_accuracy=round((
                    (tp/(tp+fn) if tp+fn else 0)+
                    (tn/(tn+fp) if tn+fp else 0))/2,6),
                brier=round(brier/total,8))


def _expanded_train(rows):
    """Hard negatives and equally legitimate controls from train projects ONLY."""
    original=[]
    for source in rows:
        original.append(source)
        for challenge,input_ in _variants(source):
            original.append(replace(
                source,
                input=input_,
                example_id=canonical_digest({
                    "source":source.example_id,
                    "train_only_metamorphic":challenge,
                    "input":input_,
                }),
                evidence=dict(source.evidence,
                              original_source_example=source.example_id,
                              source_preserving_transformation=challenge),
            ))
    if len({c.example_id for c in original})!=len(original):
        raise TrainingFlowError("repeated adversarial training sources")
    return tuple(original)


def train_robust_game_reviewer(
    plan: FlowPlan,*,authorized: bool,epochs: int=50,
    learning_rate: float=0.20,
)->dict:
    if not authorized:
        raise PermissionError("advanced original reviewer training requires owner approval")
    if not isinstance(plan,FlowPlan) or type(epochs) is not int or not 10<=epochs<=120:
        raise TrainingFlowError("typed source plan and bounded training schedule required")
    if type(learning_rate) is not float or not math.isfinite(learning_rate) or not 0.001<=learning_rate<=0.5:
        raise TrainingFlowError("finite original reviewer optimizer step required")
    rows=defaultdict(list)
    for case in plan.selected:
        if (case.project_digest not in plan.source_projects or
            case.split!=split_project(case.project_digest) or
            case.approval!="quarantined"):
            raise TrainingFlowError("foreign game/heldout split leakage")
        rows[case.split].append(case)
    split=dict(plan.split_projects)
    reasons=[]
    for s,projects in (("train",2),("validation",1),("test",1)):
        if len(split.get(s,()))<projects:
            reasons.append("insufficient_"+s+"_projects")
        if len({_label(case) for case in rows[s]})!=2:
            reasons.append("unbalanced_"+s+"_outcomes")
    common=dict(
        schema="skeleton.game_builder.experimental_reviewer_fit.v1",
        source_plan=plan.run_id,
        feature_spec=FEATURE_SPEC,
        project_counts={s:len(split.get(s,())) for s in ("train","validation","test")},
        example_counts={s:len(rows[s]) for s in ("train","validation","test")},
        no_heldout_training=True,
        metadata_attack_labels_excluded_from_feature_extractor=True,
        production_dragon_or_jeeves_weights_changed=False,
        training_artifact_approved_for_deployment=False,
    )
    if reasons:
        return dict(**common,status="blocked",reasons=reasons,training_performed=False)
    prepared=_expanded_train(rows["train"])
    if len(prepared)>40000:
        raise TrainingFlowError("consumer supervised reviewer training would exceed data budget")
    weights=[0.0]*FEATURE_DIM
    bias=0.0
    best_key=(-1.0,-1.0,-1.0)
    best=None
    train_groups=Counter(x.project_digest for x in prepared)
    for epoch in range(epochs):
        for case in sorted(prepared,key=lambda x:(x.project_digest,x.example_id)):
            probability=_probability(case,weights,bias)
            gradient=learning_rate*(_label(case)-probability)/(
                max(1,train_groups[case.project_digest])**0.5)
            bias+=gradient
            features=evidence_features(case)
            for key,value in features.items():
                weights[key]=max(-8,min(8,weights[key]*(1-0.00005*learning_rate)
                                        +gradient*value))
        # Threshold and epoch are selected *only* using validation worlds,
        # including their transformed controls. Test worlds stay untouched.
        valid=tuple(rows["validation"])
        challenged=_expanded_train(valid)
        for threshold in (0.35,0.45,0.5,0.55,0.65):
            primary=_score(valid,weights,bias,threshold)
            adversarial=_score(challenged,weights,bias,threshold)
            key=(min(primary["balanced_accuracy"],
                     adversarial["balanced_accuracy"]),
                 -adversarial["brier"],-primary["brier"])
            if key>best_key:
                best_key=key
                best=(epoch+1,threshold,tuple(weights),bias,primary,
                      adversarial)
    if best is None:
        raise TrainingFlowError("no independently verified stable checkpoint")
    epoch,threshold,fit_weights,fit_bias,val,metamo=best
    policy=dict(weights=[round(v,8) for v in fit_weights],
                bias=round(fit_bias,8),
                threshold=threshold,feature_spec=FEATURE_SPEC)
    # The test split is opened once after the candidate is locked.
    heldout=_score(rows["test"],fit_weights,fit_bias,threshold)
    heldout_challenges=_score(_expanded_train(rows["test"]),
                             fit_weights,fit_bias,threshold)
    return dict(
        **common,status="experimental_fit_only",
        epochs_selected=epoch,train=_score(rows["train"],fit_weights,fit_bias,threshold),
        train_augmented_examples=len(prepared),
        validation=val,validation_metamorphic=metamo,
        test=heldout,test_metamorphic=heldout_challenges,
        fitted_policy_digest=canonical_digest(policy),
        symbolic_policy=policy,
        promotion_requires_independent_wiki_hoag_human_rights_review=True,
        training_performed=True,
    )


__all__=[
    "FEATURE_SPEC","FEATURE_DIM","evidence_features",
    "train_robust_game_reviewer",
]
