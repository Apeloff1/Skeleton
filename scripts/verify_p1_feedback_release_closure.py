#!/usr/bin/env python3
"""Independent verifier for P1 feedback-promotion and release-SLO surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SURFACES: dict[str, tuple[str, ...]] = {
    "skeleton/learning/promotion.py": (
        "class ExperimentSpec",
        "class FeedbackLedger",
        "class EvaluationReceipt",
        "class FeedbackPromotionPipeline",
        "holdout feedback cannot enter promotion evaluation",
        "feedback cannot be retained without explicit consent",
        "def rollback(",
    ),
    "skeleton/learning/mirror_room/adversarial.py": (
        "ADVERSARIAL_ATTEMPTS_REQUIRED = 100",
        "class AdversarialMirrorRoom",
        "class AdversarialStandard",
        "class AdversarialCampaignReceipt",
        "accepted upgrade must become next baseline",
        "sealed holdout cannot be opened before attempt 100",
        "delivery is blocked until all 100 attempts complete",
        "validation baseline drifted from ratcheted standard",
        "def weighted_gain_threshold(",
        "def strict_metric_gain_threshold(",
        "retention_scenario_digests",
        "adversarial retention suite forgot prior attacks",
        "minimum_strict_metric_gain",
        "insufficient-strict-metric-lift",
        "cumulative gauntlet cannot run before attempt 100",
        "challenge_digests",
        "gauntlet_report",
        "def _observe(",
        "Observatory failures are intentionally isolated from learning",
    ),
    "skeleton/ai/learning/mirror_room/adversarial.py": (
        "ADVERSARIAL_ATTEMPTS_REQUIRED = 100",
        "class AdversarialMirrorRoom",
        "class AdversarialCampaignReceipt",
    ),
    "skeleton/learning/mirror_room/adaptation.py": (
        "class NumericDimension",
        "class DeterministicCoordinateLearner",
        "def propose(",
        "TRAIN-selected champion",
        "training_archive",
        "preferred_direction",
    ),
    "skeleton/ai/learning/mirror_room/adaptation.py": (
        "class NumericDimension",
        "class DeterministicCoordinateLearner",
    ),
    "skeleton/learning/mirror_room/memory.py": (
        "class TrainingLesson",
        "class TrainingLearningArchive",
        "def from_runs(",
        "selected_for_learning",
        "contains_validation_evidence",
        "contains_holdout_evidence",
    ),
    "skeleton/ai/learning/mirror_room/memory.py": (
        "class TrainingLesson",
        "class TrainingLearningArchive",
    ),
    "skeleton/learning/mirror_room/engine.py": (
        "candidate generator and sandbox evaluator must be independent",
        "duplicate scenario payload detected across Mirror Room corpus",
        "comparison_family_size=validation_family_size",
        "_merge_hard_examples",
        "learning_champion = production_baseline",
        "qualified_champion = production_baseline",
        "baseline=production_baseline",
        "seen_behavior_digests",
        "stagnant_generations",
    ),
    "skeleton/learning/mirror_room/replay.py": (
        "class MirrorRunReplayReceipt",
        "def verify_selected_lineage(",
        "deterministic selected lineage replay diverged",
        "sealed holdout identity changed before replay",
    ),
    "skeleton/ai/learning/mirror_room/replay.py": (
        "class MirrorRunReplayReceipt",
        "def verify_selected_lineage(",
    ),
    "skeleton/learning/mirror_room/content_quality.py": (
        "class HighEndContentConstitution",
        "class HighEndContentDeliveryDossier",
        "def qualify_high_end_content_delivery(",
        "minimum_worst_case_holdout_score",
        "minimum_attacks_per_dimension",
        "minimum_attack_families_per_dimension",
        "minimum_cumulative_validation_gain",
        "minimum_blind_judges",
        "maximum_judge_spread",
        "minimum_standard_escalation_ratio",
        "minimum_upgrades_per_quartile",
        "high-end delivery lacks sustained upgrades across all quartiles",
        "class IndependentQualityJudgeReceipt",
        "class QualityJudgePanelReceipt",
        "def _qualify_judge_panel(",
    ),
    "skeleton/ai/learning/mirror_room/content_quality.py": (
        "class HighEndContentConstitution",
        "class HighEndContentDeliveryDossier",
        "def qualify_high_end_content_delivery(",
    ),
    "skeleton/learning/mirror_room/observability.py": (
        "class MirrorMetricView",
        "class MirrorAttemptView",
        "class MirrorRoomObservatory",
        "def mirror_room_file_tree(",
        "effective_quality_score",
        "effective_detail_score",
        "production_authority",
    ),
    "skeleton/ai/learning/mirror_room/observability.py": (
        "class MirrorRoomObservatory",
        "def mirror_room_file_tree(",
    ),
    "backend/core/route_policy_catalog.py": (
        'ROUTE_POLICY_CATALOG_VERSION = "2026-10-03.v3"',
        'RouteRule("/api/mirror-room", "learning")',
    ),
    "backend/routes/mirror_room.py": (
        'prefix="/api/mirror-room"',
        '"/observatory"',
        "get_default_observatory().snapshot()",
        "mirror_room_file_tree",
    ),
    "frontend/features/MirrorRoom/MirrorRoomObservatory.tsx": (
        "100-attempt ratchet",
        "Quality ascent",
        "Selected duel",
        "Quality anatomy",
        "Integrated file tree",
        "/api/mirror-room/observatory",
    ),
    "frontend/app/mirror-room.tsx": (
        "features/MirrorRoom/MirrorRoomObservatory",
    ),
    "skeleton/testing/test_mirror_room_observability.py": (
        "test_observatory_projects_baseline_challenger_and_detail_lift",
        "test_observatory_rejected_attempt_cannot_move_visible_baseline",
        "test_observatory_file_tree_exposes_full_product_surface",
        "test_visual_observatory_is_real_route_and_not_mock_dashboard",
    ),
    "skeleton/release/slo_promotion.py": (
        "class ReleaseSLOPolicy",
        "class CanarySLOSignal",
        "class OperatorOverride",
        "class ReleaseDecisionReceipt",
        "class ReleaseSLOPromotionController",
        "operator override cannot promote failed SLO evidence",
        "release SLO signals must come from observability",
    ),
    "skeleton/testing/test_mirror_room_adversarial.py": (
        "test_full_campaign_ratchets_baseline_for_all_100_attempts",
        "test_validation_standard_floors_increase_monotonically",
        "test_rejected_attempt_never_lowers_or_replaces_baseline",
        "test_partial_campaign_cannot_touch_holdout_or_deliver",
        "test_holdout_is_opened_only_after_attempt_100",
        "test_delivery_evidence_requires_independent_verifier",
        "test_ratchet_rejects_candidate_without_meaningful_strict_metric_lift",
        "test_progressive_standard_bar_escalates_across_all_100_attempts",
        "test_every_attempt_retests_entire_discovered_attack_corpus",
        "test_observatory_failure_cannot_block_or_influence_learning",
        "test_custom_progressive_bar_can_reject_late_marginal_upgrades",
        "gauntlet_report",
    ),
    "skeleton/testing/test_mirror_room_learning.py": (
        "test_duplicate_payload_cannot_cross_learning_splits",
        "test_generator_cannot_also_be_sandbox_evaluator",
        "test_hard_example_memory_accumulates_and_prioritizes_curriculum",
        "test_validation_confidence_is_corrected_for_candidate_search_family",
        "test_validation_selection_is_blind_to_candidate_generator",
        "test_validation_qualification_never_changes_training_parent_lineage",
        "test_behaviorally_duplicate_candidate_is_rejected",
        "test_change_artifact_participates_in_behavior_identity",
        "test_stagnation_patience_stops_unproductive_search",
        "test_coordinate_learner_improves_without_custom_generator",
        "test_coordinate_learner_is_deterministic_for_same_run",
        "test_training_archive_contains_train_only_evidence",
        "test_coordinate_learner_warm_starts_from_train_archive",
        "test_selected_lineage_replay_reexecutes_exact_evidence",
        "test_selected_lineage_replay_detects_executor_divergence",
    ),
    "skeleton/testing/test_mirror_room_content_delivery.py": (
        "test_high_end_content_dossier_requires_full_ratchet_gauntlet_and_holdout",
        "test_high_end_delivery_is_blocked_before_attempt_100",
        "test_quality_constitution_requires_broad_adversarial_coverage",
        "test_quality_catalog_digest_drift_fails_closed",
        "test_high_end_delivery_rejects_non_independent_judge_panel",
        "test_canonical_high_end_constitution_is_sota_hardened",
        "test_high_end_delivery_rejects_attack_family_monoculture",
        "test_high_end_delivery_rejects_wide_blind_judge_disagreement",
    ),
    "skeleton/testing/test_feedback_promotion.py": (
        "test_assignment_is_deterministic_and_experiment_isolated",
        "test_feedback_collection_requires_consent_and_declared_data_use",
        "test_holdout_feedback_isolated_from_promotion_evaluation",
        "test_rollback_restores_baseline_with_promotion_lineage",
    ),
    "skeleton/testing/test_release_slo_promotion.py": (
        "test_healthy_observability_promotes_with_order_stable_receipt",
        "test_unhealthy_canary_automatically_rolls_back",
        "test_operator_cannot_promote_over_failed_slo_evidence",
    ),
    ".github/workflows/p1-feedback-release-closure.yml": (
        "Feedback and release contracts",
        "Independent P1 verifier",
        "test_feedback_promotion.py",
        "test_mirror_room_learning.py",
        "test_mirror_room_adversarial.py",
        "test_mirror_room_content_delivery.py",
        "test_mirror_room_observability.py",
        "test_release_slo_promotion.py",
    ),
}

EXPECTED_GAPS = {
    "gap-feedback-promotion": "feedback-learning",
    "gap-release-slo-loop": "deployment-release",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(_read(path))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests: dict[str, str] = {}

    for rel, tokens in SURFACES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"P1 closure surface is missing: {rel}")
            continue
        source = _read(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost required token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()

    construction_path = root / "machine/ai_app_construction.json"
    gap_state: dict[str, str] = {}
    if not construction_path.is_file():
        errors.append("machine/ai_app_construction.json is missing")
    else:
        construction = _load(construction_path)
        rows = construction.get("gap_register")
        if not isinstance(rows, list):
            errors.append("gap_register must be a list")
        else:
            by_id = {
                str(row.get("id")): row
                for row in rows
                if isinstance(row, dict) and row.get("id")
            }
            for gap_id, plane in EXPECTED_GAPS.items():
                row = by_id.get(gap_id)
                if row is None:
                    errors.append(f"P1 masterplan gap is missing: {gap_id}")
                    continue
                if row.get("plane") != plane:
                    errors.append(f"P1 masterplan plane drift: {gap_id}")
                status = str(row.get("status") or "")
                gap_state[gap_id] = status
                if status != "closed":
                    errors.append(
                        f"P1 masterplan gap must remain closed: {gap_id}"
                    )

    return {
        "schema_version": 1,
        "verifier": "independent-p1-feedback-release-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "valid": not errors,
        "errors": errors,
        "surface_digests": digests,
        "gap_state": gap_state,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()
    receipt = verify_repository()
    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
