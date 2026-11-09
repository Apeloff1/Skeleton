#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/functional_llm_game_builder_10mb_manifest.json"


def fail(msg: str) -> None:
    raise SystemExit("FLGB masterplan invalid: " + msg)


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("kind") != "functional-llm-game-builder-execution-atlas":
        fail("wrong kind")
    if data.get("plan_version") != "2.7.0":
        fail("unexpected plan version")

    shards = data.get("shards")
    if not isinstance(shards, list) or len(shards) != 18:
        fail("expected 18 shards")
    expected_ids = [f"FLGB-{i:02d}" for i in range(1, 19)]
    if [s.get("id") for s in shards] != expected_ids:
        fail("shard IDs are incomplete or out of order")

    coverage = data.get("coverage", {})
    lifecycle = coverage.get("lifecycle")
    proof_labels = coverage.get("proof_labels")
    stress_scenarios = coverage.get("stress_scenarios")
    if not isinstance(lifecycle, list) or len(lifecycle) != 12:
        fail("expected 12 lifecycle stages")
    if not isinstance(proof_labels, list) or len(proof_labels) != 10:
        fail("expected 10 proof labels")
    if not isinstance(stress_scenarios, list) or len(stress_scenarios) != 12:
        fail("expected 12 stress scenarios")
    policy = coverage.get("coverage_policy", {})
    for key in (
        "subsystem_lifecycle_cartesian_required",
        "evidence_class_presence_per_plane",
        "stress_scenario_presence_per_plane",
    ):
        if policy.get(key) is not True:
            fail(f"coverage policy disabled: {key}")

    legacy = data.get("legacy_requirement_baseline", {})
    expected_legacy_source = "4f2d5f736bebc30e7156d0431da18ada41664afa"
    if legacy.get("source_commit") != expected_legacy_source:
        fail("legacy requirement baseline source drift")
    legacy_per_plane = legacy.get("per_plane")
    if not isinstance(legacy_per_plane, dict):
        fail("legacy requirement baseline map missing")
    if set(legacy_per_plane) != set(expected_ids):
        fail("legacy requirement baseline plane set mismatch")
    if int(legacy.get("total_atoms", 0)) != sum(int(v) for v in legacy_per_plane.values()):
        fail("legacy requirement baseline total drift")

    total = 0
    for shard in shards:
        shard_id = shard["id"]
        path = ROOT / shard["path"]
        if not path.is_file():
            fail(f"missing {shard['path']}")
        raw = path.read_bytes()
        total += len(raw)
        per_shard_floor = int(data.get("bytes", {}).get("per_shard_minimum", 0))
        if per_shard_floor < 2_300_000:
            fail(f"per-shard minimum regressed: {per_shard_floor}")
        if int(shard.get("min_bytes", 0)) != per_shard_floor:
            fail(f"{shard_id} per-shard minimum drift")
        if len(raw) < per_shard_floor:
            fail(f"undersized {shard['path']}")
        if len(raw) != int(shard["bytes"]):
            fail(f"byte manifest stale for {shard['path']}")
        text = raw.decode("utf-8")

        if f"# {shard_id}" not in text:
            fail(f"header mismatch {shard_id}")
        if "Implementation signed: false" not in text:
            fail(f"missing unsigned implementation marker {shard_id}")
        if "Independent verification signed: false" not in text:
            fail(f"missing unsigned verification marker {shard_id}")
        if "## Coverage Closure Matrix" not in text:
            fail(f"missing coverage closure matrix {shard_id}")

        atom_ids = set(
            re.findall(rf"^## ({re.escape(shard_id)}-\d{{5}})\b", text, re.MULTILINE)
        )
        legacy_floor = int(legacy_per_plane.get(shard_id, 0))
        declared_legacy_floor = int(shard.get("legacy_baseline_requirement_atoms", 0))
        minimum_atoms = int(shard.get("minimum_requirement_atoms", 0))
        if legacy_floor <= 0:
            fail(f"missing legacy requirement baseline for {shard_id}")
        if declared_legacy_floor != legacy_floor:
            fail(f"{shard_id} legacy baseline metadata drift")
        if minimum_atoms != legacy_floor:
            fail(f"{shard_id} minimum requirement atom floor drift")
        if len(atom_ids) < legacy_floor:
            fail(
                f"legacy requirement atoms regressed in {shard_id}: "
                f"{len(atom_ids)} < {legacy_floor}"
            )

        heading_matches = re.findall(
            rf"^## {re.escape(shard_id)}-\d{{5}} — (.*?) / (.*?) / (.*?)$",
            text,
            re.MULTILINE,
        )
        if len(heading_matches) != len(atom_ids):
            fail(f"atom heading parse mismatch in {shard_id}")

        required_subsystems = shard.get("subsystems")
        if not isinstance(required_subsystems, list) or len(required_subsystems) != 12:
            fail(f"{shard_id} must register 12 subsystems")
        observed_subsystems = {sub.strip() for sub, _, _ in heading_matches}
        observed_lifecycle = {phase.strip() for _, phase, _ in heading_matches}
        if observed_subsystems != set(required_subsystems):
            fail(f"{shard_id} subsystem heading coverage mismatch")
        if observed_lifecycle != set(lifecycle):
            fail(f"{shard_id} lifecycle heading coverage mismatch")
        observed_pairs = {(sub.strip(), phase.strip()) for sub, phase, _ in heading_matches}
        expected_pairs = {(sub, phase) for sub in required_subsystems for phase in lifecycle}
        missing_pairs = expected_pairs - observed_pairs
        if missing_pairs:
            sample = sorted(missing_pairs)[:5]
            fail(f"{shard_id} missing subsystem/lifecycle pairs: {sample}")

        for index, subsystem in enumerate(required_subsystems, start=1):
            coverage_id = f"COV-{shard_id}-{index:02d}"
            if f"### {coverage_id} — {subsystem}" not in text:
                fail(f"{shard_id} missing coverage record {coverage_id}")
        for proof in proof_labels:
            if proof.lower() not in text.lower():
                fail(f"{shard_id} missing proof dimension {proof}")
        for scenario in stress_scenarios:
            if scenario.lower() not in text.lower():
                fail(f"{shard_id} missing stress dimension {scenario}")
        for token in ("Objective", "Acceptance", "Failure", "provenance", "cancellation"):
            if token.lower() not in text.lower():
                fail(f"{shard_id} missing {token} semantics")

        deep = data.get("deep_closure", {})
        required_deep = int(deep.get("required_atoms_per_plane", 0))
        if required_deep != 1296:
            fail("deep-closure per-plane atom contract drift")
        if shard.get("deep_closure_required") is not True:
            fail(f"{shard_id} deep closure not required")
        if int(shard.get("deep_closure_atoms", 0)) != required_deep:
            fail(f"{shard_id} deep-closure manifest count drift")
        if shard.get("deep_closure_pass2_required") is not True:
            fail(f"{shard_id} pass-2 deep closure not required")
        if int(shard.get("deep_closure_pass2_atoms", 0)) != required_deep:
            fail(f"{shard_id} pass-2 deep-closure manifest count drift")
        if "## Deep Functional Closure Expansion — Pass 2" not in text:
            fail(f"{shard_id} missing deep-closure pass marker")

        plane_suffix = shard_id.split("-")[-1]
        deep_matches = re.findall(
            rf"^### FLGBX-{re.escape(plane_suffix)}-(\d{{5}}) — (.*?) / (.*?) / (.*?) / (.*?)$",
            text,
            re.MULTILINE,
        )
        if len(deep_matches) != required_deep:
            fail(f"{shard_id} deep-closure atom count mismatch: {len(deep_matches)}")
        deep_ids = [ordinal for ordinal, _, _, _, _ in deep_matches]
        expected_deep_ids = [f"{i:05d}" for i in range(1, required_deep + 1)]
        if deep_ids != expected_deep_ids:
            fail(f"{shard_id} deep-closure ordinals are incomplete or out of order")

        deep_subsystems = {sub.strip() for _, sub, _, _, _ in deep_matches}
        deep_lifecycle = {phase.strip() for _, _, phase, _, _ in deep_matches}
        deep_stress = {stress.strip() for _, _, _, stress, _ in deep_matches}
        deep_proofs = {proof.strip() for _, _, _, _, proof in deep_matches}
        expected_stress = set(deep.get("stress_profiles", []))
        if deep_subsystems != set(required_subsystems):
            fail(f"{shard_id} deep-closure subsystem coverage mismatch")
        if deep_lifecycle != set(lifecycle):
            fail(f"{shard_id} deep-closure lifecycle coverage mismatch")
        if deep_stress != expected_stress:
            fail(f"{shard_id} deep-closure stress coverage mismatch")
        if deep_proofs != set(proof_labels):
            fail(f"{shard_id} deep-closure proof coverage mismatch")

        deep_cartesian = {
            (sub.strip(), phase.strip(), stress.strip())
            for _, sub, phase, stress, _ in deep_matches
        }
        expected_deep_cartesian = {
            (sub, phase, stress)
            for sub in required_subsystems
            for phase in lifecycle
            for stress in expected_stress
        }
        if deep_cartesian != expected_deep_cartesian:
            fail(f"{shard_id} deep-closure cartesian matrix incomplete")

    deep = data.get("deep_closure", {})
    if deep.get("pass_id") != "FLGB-DEEP-CLOSURE-PASS-2":
        fail("missing deep-closure pass identity")
    expected_deep_total = 1296 * len(shards)
    if int(deep.get("required_atoms_total", 0)) != expected_deep_total:
        fail("deep-closure total atom contract drift")
    if deep.get("exact_cartesian_product_required") is not True:
        fail("deep-closure exact cartesian requirement disabled")
    if deep.get("runtime_signoff_forbidden_from_specification_alone") is not True:
        fail("deep-closure runtime signoff protection disabled")

    expansion = data.get("deep_closure_expansion", {})
    if int(expansion.get("pass", 0)) != 2:
        fail("deep-closure expansion pass drift")
    if expansion.get("status") != "registered-specification":
        fail("deep-closure expansion status drift")
    if int(expansion.get("per_plane_atoms", 0)) != 1296:
        fail("deep-closure expansion per-plane count drift")
    if int(expansion.get("total_atoms", 0)) != expected_deep_total:
        fail("deep-closure expansion total count drift")
    shape = expansion.get("shape", {})
    expected_shape = {
        "planes": len(shards),
        "subsystems_per_plane": 12,
        "lifecycle_stages": len(lifecycle),
        "adversarial_profiles": len(deep.get("stress_profiles", [])),
    }
    if shape != expected_shape:
        fail("deep-closure expansion shape drift")
    if expansion.get("required_heading") != "## Deep Functional Closure Expansion — Pass 2":
        fail("deep-closure expansion heading contract drift")
    if expansion.get("atom_prefix") != "FLGBX":
        fail("deep-closure expansion atom prefix drift")
    semantics = expansion.get("semantics")
    if not isinstance(semantics, list) or len(semantics) < 6:
        fail("deep-closure expansion semantics incomplete")
    if coverage.get("deep_closure_cartesian_required") is not True:
        fail("coverage deep-closure cartesian requirement disabled")
    if coverage.get("deep_closure_adversarial_profiles") != deep.get("stress_profiles"):
        fail("coverage/deep-closure adversarial profile drift")
    for shard in shards:
        if int(shard.get("deep_closure_pass", 0)) != 2:
            fail(f"{shard['id']} deep-closure pass identity drift")
        if shard.get("deep_closure_signed") is not False:
            fail(f"{shard['id']} deep-closure specification cannot be signed")

    bytes_cfg = data.get("bytes", {})
    previous_total = int(bytes_cfg.get("previous_shard_total", 0))
    original_total = int(bytes_cfg.get("original_shard_total", 0))
    exact_double = previous_total * 2
    if previous_total <= 0:
        fail("missing previous atlas byte baseline")
    if original_total != previous_total:
        fail("original/previous atlas byte baseline drift")
    if int(bytes_cfg.get("original_surface", original_total)) != original_total:
        fail("original surface accounting drift")
    if int(bytes_cfg.get("double_baseline_target", 0)) != exact_double:
        fail("literal doubled baseline target drift")
    requested_minimum = int(bytes_cfg.get("requested_minimum", 0))
    if requested_minimum < exact_double:
        fail(f"atlas minimum is below literal doubled baseline: {requested_minimum} < {exact_double}")
    per_shard_floor = int(bytes_cfg.get("per_shard_minimum", 0))
    if int(bytes_cfg.get("per_shard_minimum_total", -1)) != per_shard_floor * len(shards):
        fail("aggregate per-shard floor accounting drift")
    if int(bytes_cfg.get("expansion_generation", 0)) != 2:
        fail("pass-2 expansion generation drift")
    for flag in ("threshold_met", "doubled_target_met", "doubled_original_surface"):
        if bytes_cfg.get(flag) is not True:
            fail(f"byte-accounting completion flag disabled: {flag}")
    if total < requested_minimum:
        fail(f"aggregate specification bytes below doubled minimum: {total}")
    if total != int(bytes_cfg["shard_total"]):
        fail("aggregate byte total stale")
    expected_growth = total - previous_total
    if int(bytes_cfg.get("pass2_net_growth", -1)) != expected_growth:
        fail("pass-2 net-growth accounting stale")
    if int(bytes_cfg.get("expansion_delta", expected_growth)) != expected_growth:
        fail("expansion-delta accounting stale")
    expected_factor = round(total / previous_total, 4)
    if round(float(bytes_cfg.get("expansion_factor", 0.0)), 4) != expected_factor:
        fail("expansion-factor accounting stale")
    if round(float(bytes_cfg.get("actual_vs_original_ratio", expected_factor)), 4) != expected_factor:
        fail("actual-vs-original ratio accounting stale")
    if bytes_cfg.get("human_index_sync_required") is not True:
        fail("human index byte-ledger synchronization disabled")
    if int(bytes_cfg.get("human_index_shard_total", -1)) != total:
        fail("human index byte ledger stale in manifest")
    human_index = ROOT / data["authorities"]["human_index"]
    if not human_index.is_file():
        fail("missing human index")
    human_text = human_index.read_text(encoding="utf-8")
    if f"{total:,}" not in human_text:
        fail("human index byte ledger stale")
    if f"{exact_double:,}" not in human_text:
        fail("human index literal doubled target stale")
    if data["completion"].get("runtime_completion_claim") is not False:
        fail("runtime completion must remain fail-closed")
    if data["completion"].get("implementation_signed") is not False:
        fail("implementation cannot be auto-signed")
    if data["completion"].get("independent_verification_signed") is not False:
        fail("verification cannot be auto-signed")
    if coverage.get("required_planes") != expected_ids:
        fail("coverage planes mismatch")
    if not coverage.get("plan_surface_no_known_unmapped_primary_domain"):
        fail("plan coverage assertion missing")

    e2e = data.get("end_to_end_acceptance", [])
    if not isinstance(e2e, list) or len(e2e) < 12:
        fail("end-to-end spine incomplete")

    frontier = data.get("frontier_competition")
    if not isinstance(frontier, dict):
        fail("frontier competition contract missing")
    if frontier.get("status") != "specification-registered-evidence-pending":
        fail("frontier competition status drift")
    if frontier.get("completion_claim") is not False:
        fail("frontier competition completion must remain fail-closed")
    if frontier.get("implementation_signed") is not False:
        fail("frontier competition implementation cannot be auto-signed")
    if frontier.get("independent_verification_signed") is not False:
        fail("frontier competition verification cannot be auto-signed")

    comparator = frontier.get("comparator_policy")
    if not isinstance(comparator, dict):
        fail("frontier comparator policy missing")
    if int(comparator.get("minimum_frontier_comparators", 0)) < 3:
        fail("frontier competition requires at least three frontier comparators")
    for key in (
        "strongest_available_comparator_required",
        "exact_identity_required",
        "same_or_disclosed_budget_required",
        "contamination_controls_required",
        "public_and_heldout_mix_required",
        "benchmark_cherry_picking_forbidden",
    ):
        if comparator.get(key) is not True:
            fail(f"frontier comparator policy disabled: {key}")
    max_age = comparator.get("maximum_comparator_age_days")
    if not isinstance(max_age, int) or max_age <= 0 or max_age > 90:
        fail("frontier comparator freshness must be bounded to 90 days")

    frontier_domains = frontier.get("required_domains")
    expected_frontier_ids = [f"FC-{index:02d}" for index in range(1, 13)]
    if not isinstance(frontier_domains, list) or [
        item.get("id") if isinstance(item, dict) else None
        for item in frontier_domains
    ] != expected_frontier_ids:
        fail("frontier competition domain coverage drift")
    if any(
        not isinstance(item.get("name"), str) or not item["name"].strip()
        or not isinstance(item.get("critical"), bool)
        for item in frontier_domains
    ):
        fail("frontier competition domains malformed")

    promotion = frontier.get("promotion_rules")
    if not isinstance(promotion, dict):
        fail("frontier promotion rules missing")
    required_promotion_rules = (
        "per_domain_results_required",
        "statistical_uncertainty_required",
        "blind_human_evaluation_required_for_subjective_quality",
        "no_critical_domain_may_be_hidden_by_aggregate_score",
        "safety_privacy_authority_rights_and_recovery_are_non_compensable",
        "game_builder_target_requires_frontier_parity_or_better",
        "long_horizon_consistency_target_requires_frontier_parity_or_better",
        "coding_repository_engineering_target_requires_frontier_parity_or_better",
        "dual_rival_gain_must_be_measured_against_single_pass_baseline",
        "regressions_against_current_champion_block_promotion",
        "exact_head_evidence_required",
        "independent_verification_required",
    )
    for key in required_promotion_rules:
        if promotion.get(key) is not True:
            fail(f"frontier promotion rule disabled: {key}")

    frontier_evidence = frontier.get("required_evidence")
    if not isinstance(frontier_evidence, list) or len(frontier_evidence) < 10:
        fail("frontier competition evidence bundle incomplete")
    required_modes = frontier.get("evaluation_modes")
    if not isinstance(required_modes, list) or len(required_modes) < 8:
        fail("frontier competition evaluation modes incomplete")
    for token in (
        "frontier",
        "blind human",
        "heldout",
        "exact-head",
        "independent verification",
    ):
        corpus = " ".join(
            [str(frontier.get("objective", "")), str(frontier.get("target_interpretation", ""))]
            + [str(item) for item in frontier_evidence]
            + [str(item) for item in required_modes]
        ).lower()
        if token not in corpus:
            fail(f"frontier competition contract missing {token}")


    if frontier.get("protocol_version") != "2.0":
        fail("frontier competition protocol version drift")

    measurement = frontier.get("measurement_constitution")
    if not isinstance(measurement, dict):
        fail("frontier measurement constitution missing")
    expected_measurement = {
        "preregistration_required": True,
        "immutable_task_manifest_before_candidate_run": True,
        "minimum_independent_runs_per_scored_task": 6,
        "paired_task_assignment_required": True,
        "fixed_seed_set_or_seed_manifest_required": True,
        "critical_domain_noninferiority_required": True,
        "equal_budget_head_to_head_required": True,
        "unconstrained_quality_ceiling_run_required": True,
        "compute_normalized_pareto_frontier_required": True,
        "quality_per_cost_and_quality_per_wall_clock_required": True,
        "raw_trajectory_retention_required": True,
        "failed_and_aborted_runs_retained": True,
        "selective_rerun_cherry_picking_forbidden": True,
    }
    for key, expected in expected_measurement.items():
        if measurement.get(key) != expected:
            fail(f"frontier measurement constitution drift: {key}")
    if float(measurement.get("confidence_interval_level", 0.0)) < 0.95:
        fail("frontier confidence interval floor weakened")
    if float(measurement.get("non_inferiority_margin_pp_max", 99.0)) > 2.0:
        fail("frontier non-inferiority margin weakened")
    if int(measurement.get("minimum_parity_or_better_domains", 0)) < 10:
        fail("frontier parity domain floor weakened")
    if int(measurement.get("minimum_superior_core_targets", 0)) < 2:
        fail("frontier superior core-target floor weakened")

    if int(comparator.get("minimum_independent_runs_per_scored_task", 0)) < 6:
        fail("frontier comparator trial-count floor weakened")
    for key in (
        "hidden_challenge_rotation_required",
        "scaffold_and_tooling_parity_or_disclosure_required",
        "reward_hacking_review_required",
        "reusable_heldout_after_exposure_forbidden",
        "model_family_provider_diversity_documented",
    ):
        if comparator.get(key) is not True:
            fail(f"frontier comparator protocol disabled: {key}")
    if int(comparator.get("maximum_comparator_age_days", 999)) > 45:
        fail("frontier comparator freshness must be bounded to 45 days")

    long_horizon = frontier.get("long_horizon_protocol")
    if not isinstance(long_horizon, dict):
        fail("frontier long-horizon protocol missing")
    buckets = long_horizon.get("human_equivalent_duration_buckets_hours")
    if not isinstance(buckets, list) or len(buckets) < 6 or max(buckets) < 160:
        fail("frontier long-horizon duration coverage incomplete")
    for key in (
        "multi_session_resume_required",
        "forced_context_reset_trials_required",
        "checkpoint_reopen_trials_required",
        "state_drift_measurement_required",
        "canon_and_requirement_drift_measurement_required",
        "cumulative_error_growth_curve_required",
        "recovery_after_interruption_required",
        "multi_day_project_tasks_required",
        "long_horizon_score_may_not_be_inferred_from_short_task_average",
    ):
        if long_horizon.get(key) is not True:
            fail(f"frontier long-horizon control disabled: {key}")
    curves = long_horizon.get("success_curves_required")
    if not isinstance(curves, list) or "50%-success time horizon" not in curves or "80%-success time horizon" not in curves:
        fail("frontier long-horizon 50%/80% success curves missing")

    anti_gaming = frontier.get("anti_gaming_protocol")
    if not isinstance(anti_gaming, dict):
        fail("frontier anti-gaming protocol missing")
    for key in (
        "reward_hacking_detection_required",
        "benchmark_leakage_scan_required",
        "test_oracle_introspection_forbidden",
        "evaluator_manipulation_forbidden",
        "simulator_or_harness_tampering_forbidden",
        "unauthorized_external_solution_lookup_forbidden",
        "hidden_test_inference_without_task_evidence_flagged",
        "prompt_injection_against_evaluators_tested",
        "suspicious_success_manual_review_required",
        "cheating_or_policy_bypass_scores_zero",
        "raw_tool_and_action_trace_review_required",
    ):
        if anti_gaming.get(key) is not True:
            fail(f"frontier anti-gaming control disabled: {key}")

    evaluator = frontier.get("evaluator_independence")
    if not isinstance(evaluator, dict):
        fail("frontier evaluator-independence contract missing")
    if int(evaluator.get("minimum_independent_evaluator_implementations", 0)) < 2:
        fail("frontier evaluator independence floor weakened")
    for key in (
        "candidate_self_score_never_decisive",
        "blind_human_tribunal_required_for_subjective_core_outputs",
        "evaluator_identity_and_version_pinned",
        "evaluator_prompt_and_rubric_version_pinned",
        "evaluator_disagreement_report_required",
        "collusion_and_shared_failure_mode_review_required",
        "adjudication_receipt_required",
    ):
        if evaluator.get(key) is not True:
            fail(f"frontier evaluator-independence control disabled: {key}")

    dominance = frontier.get("dominance_rule")
    if not isinstance(dominance, dict):
        fail("frontier dominance rule missing")
    if int(dominance.get("minimum_parity_or_better_domains", 0)) < 10:
        fail("frontier dominance parity floor weakened")
    if int(dominance.get("minimum_superior_core_targets", 0)) < 2:
        fail("frontier dominance superiority floor weakened")
    for key in (
        "critical_domains_must_meet_preregistered_non_inferiority_margin",
        "dual_rival_equal_budget_ablation_required",
        "dual_rival_extra_compute_control_required",
        "strongest_comparator_head_to_head_required",
        "current_champion_regression_veto",
        "aggregate_score_never_overrides_critical_gate",
    ):
        if dominance.get(key) is not True:
            fail(f"frontier dominance control disabled: {key}")
    core_targets = dominance.get("core_targets")
    if not isinstance(core_targets, list) or len(core_targets) < 4:
        fail("frontier dominance core-target set incomplete")

    game_challenge = frontier.get("game_builder_challenge")
    if not isinstance(game_challenge, dict):
        fail("frontier game-builder challenge contract missing")
    for key in (
        "brief_to_playable_export_required",
        "reopen_and_continue_after_clean_restart_required",
        "cross_scene_and_cross_session_canon_consistency_required",
        "gameplay_loop_quality_and_debugging_required",
        "asset_code_narrative_rights_provenance_required",
        "performance_budget_and_frame_time_evidence_required",
        "accessibility_localization_and_input_equivalence_required",
        "save_migration_mod_sandbox_and_network_fault_trials_required",
        "blind_player_or_expert_judging_required",
    ):
        if game_challenge.get(key) is not True:
            fail(f"frontier game-builder challenge disabled: {key}")

    shard17 = (ROOT / shards[16]["path"]).read_text(encoding="utf-8")
    for token in ("Forge-100", "Forge-1000", "Forge-10000", "rights", "clean-room"):
        if token.lower() not in shard17.lower():
            fail(f"rival/rights plane missing {token}")

    shard14 = (ROOT / shards[13]["path"]).read_text(encoding="utf-8")
    for token in ("longform", "canon", "continuity", "timeline"):
        if token.lower() not in shard14.lower():
            fail(f"long-form plane missing {token}")

    print(
        f"FLGB masterplan valid: {len(shards)} shards, {total} bytes, "
        "18x12 subsystem/lifecycle coverage matrices plus 23,328 deep-closure atoms present, "
        "runtime completion remains unsigned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
