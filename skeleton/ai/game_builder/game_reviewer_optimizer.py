"""Real validation-only hyperparameter competition for the local game reviewer.

Every challenger is trained on TRAIN games and selected using VALIDATION only.
Only the final frozen winner may inspect the protected TEST partition; the
optimizer returns an experimental fit and qualification, NOT a deployment.
Wiki/HOAG/Dragon research is advisory context, never unlicensed gradient data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

from .contracts import canonical_digest
from .game_training_flow import FlowPlan, TrainingFlowError
from .game_reviewer_v2 import train_robust_game_reviewer
from .game_model_promotion import (
    PromotionError, PromotionStandard, PromotionEvaluation,
    evaluate_candidate, validate_policy,
)


@dataclass(frozen=True, slots=True)
class OptimizerSchedule:
    learning_rates: tuple[float, ...] = (0.08, 0.16, 0.28)
    epochs: tuple[int, ...] = (30, 60)
    max_trials: int = 6

    def __post_init__(self):
        if (type(self.learning_rates) is not tuple or not 1<=len(self.learning_rates)<=4
                or type(self.epochs) is not tuple or not 1<=len(self.epochs)<=4
                or type(self.max_trials) is not int or not 1<=self.max_trials<=12
                or len(self.learning_rates)*len(self.epochs)>self.max_trials):
            raise PromotionError("bounded complete deterministic hyperparameter lattice required")
        if (any(type(x) is not float or not math.isfinite(x) or not 0.001<=x<=0.5
                for x in self.learning_rates)
                or len(set(self.learning_rates))!=len(self.learning_rates)
                or any(type(x) is not int or not 10<=x<=120 for x in self.epochs)
                or len(set(self.epochs))!=len(self.epochs)):
            raise PromotionError("invalid non-distinct optimizer schedule")

    def payload(self):
        return dict(learning_rates=list(self.learning_rates),
                    epochs=list(self.epochs),max_trials=self.max_trials)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    plan_digest: str
    optimizer_digest: str
    trial_receipts: tuple[dict[str, Any], ...]
    winner_index: int | None
    selected_fit: dict | None
    promotion_evaluation: PromotionEvaluation | None
    champion_digest: str | None

    @property
    def candidate_improved(self):
        return self.promotion_evaluation is not None and self.promotion_evaluation.passed

    def payload(self):
        # Never expose a validation-only candidate as a deployable policy;
        # actual weights remain in the *explicit* selected_fit artifact.
        return dict(
            schema="skeleton.game_builder.actual_weight_optimization.v1",
            plan_digest=self.plan_digest,
            optimizer_digest=self.optimizer_digest,
            trial_receipts=list(self.trial_receipts),
            winner_index=self.winner_index,
            winner_policy_digest=(
                self.selected_fit["fitted_policy_digest"] if self.selected_fit else None),
            qualification=self.promotion_evaluation.payload()
                if self.promotion_evaluation else None,
            champion_digest=self.champion_digest,
            independent_test_used_for_search=False,
            protected_test_evaluated_for_frozen_winner=bool(self.selected_fit),
            actual_sgd_weights_updated=bool(self.selected_fit),
            core_jeeves_dragon_llm_parameters_modified=False,
            hoag_or_wiki_authorized_weight_mutation=False,
            deployment_authorized=False,
            needs_separate_operator_stage_and_live_review=True,
        )


def _rank(fit: dict):
    if fit.get("status")!="validation_selection_only" or fit.get("test") is not None:
        raise PromotionError("optimizer trial opened sealed TEST or lacked real fitting")
    val=fit["validation"]
    challenge=fit["validation_metamorphic"]
    if (type(val) is not dict or type(challenge) is not dict
            or min(val["n"],challenge["n"])<2):
        raise PromotionError("actual independent validation and redteam evaluation required")
    for item in (val,challenge):
        if any(not math.isfinite(item[k]) for k in ("balanced_accuracy","brier")):
            raise PromotionError("invalid optimization objective")
    # Exact same score definition for every tested schedule. Penalize
    # overfitting to ordinary validation through minimum of both measures.
    return (round(min(val["balanced_accuracy"],challenge["balanced_accuracy"]),6),
            round(-challenge["brier"],8),round(-val["brier"],8))


def optimize_review_weights(plan: FlowPlan, *, authorized: bool,
                            schedule: OptimizerSchedule=OptimizerSchedule(),
                            standard: PromotionStandard=PromotionStandard(),
                            champion: dict | None=None) -> OptimizationResult:
    if not authorized:
        raise PermissionError("local model weight optimization requires operator approval")
    if (not isinstance(plan,FlowPlan) or not isinstance(schedule,OptimizerSchedule)
            or not isinstance(standard,PromotionStandard)):
        raise PromotionError("typed source plan and frozen quality standards required")
    if champion is not None:
        validate_policy(champion)
    trials=[]
    winning=None
    selected_params=None
    best_key=None
    for epochs in schedule.epochs:
        for step in schedule.learning_rates:
            fit=train_robust_game_reviewer(
                plan,authorized=True,epochs=epochs,
                learning_rate=step,evaluate_test=False)
            if fit.get("status")!="validation_selection_only":
                raise PromotionError("no valid independently trained candidate available")
            key=_rank(fit)
            record=dict(
                index=len(trials),epochs=epochs,learning_rate=step,
                selected_epoch=fit["epochs_selected"],
                validation=fit["validation"],
                validation_metamorphic=fit["validation_metamorphic"],
                policy_digest=fit["fitted_policy_digest"],
                actual_trained_weights=True,
                protected_test_opened=False,
                winner_selection_metric=list(key),
            )
            trials.append(record)
            # Ties prefer fewer epochs and smaller learning rate, NOT results
            # secretly inspected from TEST or knowledge/source articles.
            selection=(*key,-epochs,-step)
            if best_key is None or selection>best_key:
                best_key=selection
                winning=len(trials)-1
                selected_params=(epochs,step,fit)
    if selected_params is None:
        raise PromotionError("optimizer produced no finite real candidate")
    epochs,step,selection_fit=selected_params
    # Open TEST only AFTER the complete schedule and winner are sealed.
    final_fit=train_robust_game_reviewer(
        plan,authorized=True,epochs=epochs,learning_rate=step,
        evaluate_test=True)
    if (final_fit.get("fitted_policy_digest")!=selection_fit["fitted_policy_digest"]
            or final_fit.get("validation")!=selection_fit["validation"]
            or final_fit.get("validation_metamorphic")!=selection_fit["validation_metamorphic"]
            or final_fit.get("protected_test_opened") is not True):
        raise PromotionError("nonreproducible fit would invalidate final qualification")
    evaluation=evaluate_candidate(plan,final_fit,standard=standard,
                                  champion=champion,authorized=True)
    return OptimizationResult(
        canonical_digest(plan.payload()),
        canonical_digest(schedule.payload()),
        tuple(trials),winning,final_fit,evaluation,
        canonical_digest(champion) if champion else None,
    )


__all__=["OptimizerSchedule","OptimizationResult","optimize_review_weights"]
