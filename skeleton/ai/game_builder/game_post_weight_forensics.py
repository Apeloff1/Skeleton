"""Post-weight-addition forensic analysis for the REAL local game reviewer.

Analyze a candidate *after* its SGD weights have actually changed, without
pretending the shadow candidate was installed. Recompute independent frozen
TEST/validation evaluation rather than trusting stored summaries, quantify
parameter motion, per-game and adversarial-family regression, calibration,
critical misses and promotion rationale. Feed only AGGREGATED failure categories
into Dragon research: no held-out game IDs, labels, examples or predictions
enter prompts or subsequent gradient batches.

Jeeves/Dragon foundation weights are never touched by this local ranker audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt,isfinite

from .contracts import canonical_digest
from .game_training_flow import FlowPlan
from .game_model_promotion import (
    PromotionError,PromotionStandard,validate_policy,evaluate_candidate,
)
from .game_reviewer_optimizer import OptimizationResult
from .game_learning_feedback import (
    ImprovementLedger,feedback_from_evaluation,
)

WEIGHT_SAFETY_ABS_DELTA=8.1
GROUP_TYPES=("train","validation","test")


@dataclass(frozen=True,slots=True)
class PostWeightReport:
    plan_digest: str
    model_before_digest: str|None
    model_after_digest: str
    original_optimizer_digest: str
    standard_digest: str
    evaluation_digest: str
    changed_coordinates: int
    dimensionality: int
    weight_l1_change: float|None
    weight_l2_change: float|None
    weight_linf_change: float|None
    bias_delta: float|None
    threshold_delta: float|None
    relative_weight_drift: float|None
    split_deltas: tuple[dict,...]
    family_aggregate: tuple[dict,...]
    safety_objections: tuple[str,...]
    feedback: ImprovementLedger
    shadow_fit_qualified: bool
    measured_better_than_champion: bool
    independent_live_usage_verified: bool=False
    actual_active_installation_verified: bool=False

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.post_weight_forensic_analysis.v1",
            plan_digest=self.plan_digest,
            model_before_digest=self.model_before_digest,
            model_after_digest=self.model_after_digest,
            optimizer_digest=self.original_optimizer_digest,
            standard_digest=self.standard_digest,
            evaluation_digest=self.evaluation_digest,
            changed_coordinates=self.changed_coordinates,
            dimensionality=self.dimensionality,
            weight_l1_change=self.weight_l1_change,
            weight_l2_change=self.weight_l2_change,
            weight_linf_change=self.weight_linf_change,
            bias_delta=self.bias_delta,
            threshold_delta=self.threshold_delta,
            relative_weight_drift=self.relative_weight_drift,
            split_deltas=list(self.split_deltas),
            family_aggregate=list(self.family_aggregate),
            safety_objections=list(self.safety_objections),
            quality_feedback_digest=self.feedback.digest,
            quality_feedback=self.feedback.payload(),
            shadow_fit_qualified=self.shadow_fit_qualified,
            measured_better_than_champion=self.measured_better_than_champion,
            independent_live_usage_verified=self.independent_live_usage_verified,
            actual_active_installation_verified=self.actual_active_installation_verified,
            heldout_case_ids_exported=False,
            protected_eval_data_reused_for_training=False,
            no_core_jeeves_dragon_weight_update=True,
            no_automatic_model_promotion=True)


def _safe_delta(a,b):
    value=round(a-b,9)
    if not isfinite(value):
        raise PromotionError("nonfinite weight delta in forensic model")
    return value


def analyze_post_weight_change(
    plan: FlowPlan,
    optimization: OptimizationResult, *,
    standard: PromotionStandard,
    champion: dict|None,
    authorized: bool,
    max_relative_drift: float=3.0,
)->PostWeightReport:
    if not authorized:
        raise PermissionError("post-weight reviewer auditing requires operator access")
    if (not isinstance(plan,FlowPlan)
            or not isinstance(optimization,OptimizationResult)
            or not isinstance(standard,PromotionStandard)
            or type(max_relative_drift) is not float
            or not isfinite(max_relative_drift)
            or not 0.01<=max_relative_drift<=8.0
            or optimization.plan_digest!=canonical_digest(plan.payload())
            or optimization.promotion_evaluation is None
            or optimization.selected_fit is None
            or optimization.winner_index is None
            or optimization.winner_index not in range(len(optimization.trial_receipts))):
        raise PromotionError("source-bound real optimized weights and exact winner required")
    fit=optimization.selected_fit
    policy=validate_policy(fit.get("symbolic_policy"))
    if (fit.get("status")!="experimental_fit_only"
            or fit.get("training_performed") is not True
            or fit.get("source_plan")!=plan.run_id
            or fit.get("protected_test_opened") is not True
            or canonical_digest(policy)!=fit.get("fitted_policy_digest")
            or fit.get("fitted_policy_digest")!=optimization.trial_receipts[
                optimization.winner_index]["policy_digest"]):
        raise PromotionError("after-weight checkpoint or selected validation receipt is altered")
    if champion is not None:
        validate_policy(champion)
    leader_digest=canonical_digest(champion) if champion else None
    if leader_digest!=optimization.champion_digest:
        raise PromotionError("post-weight analysis changed installed champion reference")
    prior=optimization.promotion_evaluation
    if prior.standard_digest!=standard.digest:
        raise PromotionError("model quality frontier changed after training")
    independently_verified=evaluate_candidate(
        plan,fit,standard=standard,champion=champion,authorized=True)
    if independently_verified.digest!=prior.digest:
        raise PromotionError("post-weight replay no longer matches sealed independent evaluation")
    feedback=feedback_from_evaluation(independently_verified,authorized=True)
    objections=set(independently_verified.blockers)
    if not optimization.ready_for_stage:
        objections.add("not_qualified_for_shadow_staging_or_no_measurable_uplift")
    if policy["feature_spec"]!="normalized_game_evidence_256_v2":
        objections.add("unsupported_for_second_glance_model_features")
    if champion is not None and champion["feature_spec"]!=policy["feature_spec"]:
        objections.add("candidate_champion_feature_encoding_changed")
    if champion is None:
        changed=len([x for x in policy["weights"] if abs(x)>1e-9])
        l1=l2=linf=bias=threshold=ratio=None
    else:
        diffs=[_safe_delta(a,b) for a,b in zip(
            policy["weights"],champion["weights"])]
        changed=sum(abs(x)>1e-9 for x in diffs)
        l1=round(sum(abs(x) for x in diffs),9)
        l2=round(sqrt(sum(x*x for x in diffs)),9)
        linf=round(max(map(abs,diffs)),9)
        bias=_safe_delta(policy["bias"],champion["bias"])
        threshold=_safe_delta(policy["threshold"],champion["threshold"])
        norm=sqrt(sum(x*x for x in champion["weights"]))
        ratio=round(l2/max(norm,0.001),9)
        if ratio>max_relative_drift:
            objections.add("excessive_model_parameter_drift_needs_manual_review")
        if linf>WEIGHT_SAFETY_ABS_DELTA:
            objections.add("unexpected_coordinate_jump")
    if changed==0:
        objections.add("no_real_parameter_coordinates_changed")
    metrics=independently_verified.metrics
    details=[]
    for split in GROUP_TYPES:
        current=metrics[split]
        prior_metric=(metrics.get("champion") or {}).get(split)
        if prior_metric is None:
            delta_accuracy=delta_brier=delta_critical=None
        else:
            delta_accuracy=round(current["balanced_accuracy"]-
                                 prior_metric["balanced_accuracy"],6)
            delta_brier=round(prior_metric["brier"]-current["brier"],8)
            old_critical=prior_metric["critical_recall"]
            new_critical=current["critical_recall"]
            delta_critical=(None if old_critical is None or new_critical is None
                            else round(new_critical-old_critical,6))
            if delta_accuracy < -1e-6:
                objections.add("protected_"+split+"_accuracy_regression")
            if delta_brier < -1e-8:
                objections.add("protected_"+split+"_calibration_regression")
            if delta_critical is not None and delta_critical < -1e-6:
                objections.add("protected_"+split+"_critical_recall_regression")
        details.append(dict(
            split=split,observed_games=len(dict(current["projects"])),
            observed_replays=current["n"],balanced_accuracy=current["balanced_accuracy"],
            brier=current["brier"],critical_recall=current["critical_recall"],
            balanced_accuracy_gain=delta_accuracy,
            brier_improvement=delta_brier,
            critical_recall_gain=delta_critical,
            raw_project_ids_released=False))
    families={}
    # Publish ONLY per-family aggregate counts; never leak protected
    # example IDs, exact scenario text, predicted labels or project hashes.
    for split in ("validation","test"):
        for name,item in metrics[split]["attacks"].items():
            key=canonical_digest(name)
            rec=families.setdefault(key,[0,0,0])
            rec[0]+=item["n"]
            rec[1]+=item["correct"]
            rec[2]+=item["missed_dangers"]
    summary=tuple(dict(
        family_digest=digest,replay_count=n,correct=correct,
        critical_misses=missed,
        requires_new_train_only_counterexample=bool(missed),
        sealed_replay_content_exposed=False)
        for digest,(n,correct,missed) in sorted(families.items()))
    if any(item["critical_misses"] for item in summary):
        objections.add("independent_evaluation_found_missed_dangers")
    return PostWeightReport(
        optimization.plan_digest,leader_digest,canonical_digest(policy),
        optimization.optimizer_digest,standard.digest,
        independently_verified.digest,changed,len(policy["weights"]),
        l1,l2,linf,bias,threshold,ratio,tuple(details),summary,
        tuple(sorted(objections)),feedback,
        independently_verified.passed and not objections,
        optimization.candidate_improved,False,False)


__all__=["PostWeightReport","analyze_post_weight_change"]
