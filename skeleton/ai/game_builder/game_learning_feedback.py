"""Source-safe, evidence-bound learning objectives for the game reviewer.

The advisor never trains a model, edits a held-out split, installs weights or
authorizes gameplay. It converts *all* failed qualification gates into a
deterministic, bounded learning agenda. Only newly acquired, independently
reviewed TRAIN-project evidence may be turned into gradient updates; protected
validation/test and live cohorts remain evaluation-only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .contracts import canonical_digest
from .game_model_promotion import PromotionError, PromotionEvaluation

_REASONS = (
    ("champion_per_game_regression", "regression", 100),
    ("champion_quality_regression", "regression", 100),
    ("live_project_regression", "regression", 100),
    ("unhandled_attack_family", "adversarial_escape", 100),
    ("missed_attack_family", "adversarial_escape", 100),
    ("high_severity_recall", "danger_recall", 100),
    ("critical_recall", "danger_recall", 100),
    ("reviewer_shortcut_detection", "metamorphic_robustness", 95),
    ("counterfactual", "metamorphic_robustness", 95),
    ("uncertain_danger_recall", "recall_confidence", 90),
    ("recall_confidence", "recall_confidence", 90),
    ("live_class_support", "class_coverage", 85),
    ("insufficient_each_class", "class_coverage", 85),
    ("insufficient_independent_projects", "project_diversity", 85),
    ("unrepresented_project", "project_diversity", 85),
    ("thin_attack_family", "family_coverage", 85),
    ("live_family_coverage", "family_coverage", 85),
    ("game_specific_regression", "project_quality", 80),
    ("balanced_accuracy", "balanced_quality", 80),
    ("generalization_gap", "generalization", 80),
    ("calibration_error", "calibration", 70),
    ("probability_calibration", "calibration", 70),
)
_ACTIONS = {
    "regression": "Acquire original TRAIN games exercising the failed behavior; preserve the incumbent and rerun independent non-regression evaluation.",
    "adversarial_escape": "Construct canonically replayed TRAIN-only hostile incidents and matched genuine controls; require zero unhandled critical hazards.",
    "danger_recall": "Collect high-severity, independent TRAIN game replays with counterbalancing benign cases; verify zero critical misses.",
    "metamorphic_robustness": "Adversarially perturb TRAIN-only source-preserving metadata and envelopes; exclude every held-out counterexample from gradients.",
    "recall_confidence": "Increase the number of distinct verified TRAIN games, not repeated samples of one world; reseal fresh evaluation games.",
    "class_coverage": "Acquire positive and negative replay evidence from new TRAIN projects without synthetic label inflation.",
    "project_diversity": "Add independently authored original TRAIN projects and sealed separate validation/test projects.",
    "family_coverage": "Expand underrepresented attack families on new TRAIN worlds, with matching verified-control demonstrations.",
    "project_quality": "Resolve weakest original-game quality lanes with project-balanced TRAIN examples; retain per-game regression vetoes.",
    "balanced_quality": "Rebalance real TRAIN incidents and genuine controls and refit using validation-only checkpoint selection.",
    "generalization": "Expand independent TRAIN world diversity; use newly sealed held-out games to measure cross-world generalization.",
    "calibration": "Refit probability calibration from TRAIN and validation evidence only, freezing the untouched test suite.",
    "frontier_expansion": "Raise at least one monotonic standard and collect previously unseen original games and attack families before proposing the next candidate.",
}


@dataclass(frozen=True, slots=True)
class ImprovementLedger:
    source_digest: str
    candidate_digest: str
    phase: str
    quality_passed: bool
    blocker_count: int
    objectives: tuple[dict[str, Any], ...]

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict:
        return dict(
            schema="skeleton.game_builder.adversarial_learning_ledger.v1",
            source_digest=self.source_digest,
            candidate_digest=self.candidate_digest,
            phase=self.phase,
            quality_passed=self.quality_passed,
            blockers_accounted_for=self.blocker_count,
            objective_count=len(self.objectives),
            objectives=list(self.objectives),
            permitted_training_source="new_source_reviewed_train_projects_only",
            validation_test_usage_idle_examples_may_be_trained_on=False,
            requires_frozen_independent_re_evaluation=True,
            requires_unchanged_or_stronger_standards=True,
            auto_deployment=False,
            model_promotion_approved=False,
            canonical_gameplay_authority_unchanged=True,
        )


def _categorize(reason: str) -> tuple[str, int]:
    if not isinstance(reason, str) or not 1 <= len(reason) <= 256:
        raise PromotionError("invalid or unbounded reviewer qualification failure")
    for needle, category, priority in _REASONS:
        if needle in reason:
            return category, priority
    return "unclassified_gap", 100


def _ledger(*, source_digest: str, candidate_digest: str, phase: str,
            quality_passed: bool, blockers: tuple[str, ...]) -> ImprovementLedger:
    # All categories are accounted for; never silently cut an incomplete
    # failure set down to a convenient number of tasks.
    if (type(quality_passed) is not bool
            or phase not in {"frozen_evaluation", "usage", "idle"}
            or not isinstance(source_digest, str) or len(source_digest) != 64
            or not isinstance(candidate_digest, str) or len(candidate_digest) != 64
            or type(blockers) is not tuple or len(blockers) > 4096):
        raise PromotionError("complete typed learning evidence required")
    groups = Counter()
    for reason in blockers:
        category, _ = _categorize(reason)
        groups[category] += 1
    if quality_passed != (len(blockers) == 0):
        raise PromotionError("learning verdict conflicts with independent quality evidence")
    if not groups:
        groups["frontier_expansion"] = 0
    if len(groups) > 32:
        raise PromotionError("unbounded learning categories need human triage")
    tasks = []
    for category, count in groups.items():
        priority = next((score for _, cat, score in _REASONS if cat == category), 100)
        if category == "frontier_expansion":
            priority = 50
        action = _ACTIONS.get(category,
                              "Investigate the full evaluator ledger, acquire new independent TRAIN evidence, and preserve sealed tests.")
        tasks.append(dict(
            priority=priority, category=category,
            affected_gate_count=count, action=action,
            train_only=True, requires_new_original_sources=True,
            human_and_mirror_review_required=True,
            heldout_case_ids_exported=False,
            complete=False,
        ))
    tasks.sort(key=lambda x: (-x["priority"], x["category"]))
    return ImprovementLedger(source_digest, candidate_digest, phase,
                             quality_passed, len(blockers), tuple(tasks))


def feedback_from_evaluation(evaluation: PromotionEvaluation, *,
                             authorized: bool) -> ImprovementLedger:
    if not authorized:
        raise PermissionError("independent model feedback requires operator authority")
    if not isinstance(evaluation, PromotionEvaluation):
        raise PromotionError("verified candidate evaluation required")
    return _ledger(source_digest=evaluation.digest,
                   candidate_digest=evaluation.candidate_digest,
                   phase="frozen_evaluation", quality_passed=evaluation.passed,
                   blockers=evaluation.blockers)


def feedback_from_cohort(cohort: dict, *, mode: str,
                         authorized: bool) -> ImprovementLedger:
    if not authorized:
        raise PermissionError("observed model feedback requires operator authority")
    if (type(cohort) is not dict
            or cohort.get("schema") != "skeleton.game_builder.fresh_cohort.v1"
            or type(cohort.get("blockers")) is not list
            or type(cohort.get("passed")) is not bool
            or not isinstance(cohort.get("candidate_digest"), str)):
        raise PromotionError("independent game cohort evidence required")
    return _ledger(source_digest=canonical_digest(cohort),
                   candidate_digest=cohort["candidate_digest"],
                   phase=mode, quality_passed=cohort["passed"],
                   blockers=tuple(cohort["blockers"]))


__all__ = ["ImprovementLedger", "feedback_from_evaluation", "feedback_from_cohort"]
