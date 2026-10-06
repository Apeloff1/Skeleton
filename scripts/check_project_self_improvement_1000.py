#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "project_self_improvement_1000.json"
EPOCH_PATH = ROOT / "machine" / "project_self_improvement_epoch_contract.json"
SCHEDULER_PATH = ROOT / "machine" / "project_self_improvement_idle_scheduler.json"

MATURITY = [
    "planned","specified","implemented","integrated",
    "independently_verified","adversarially_qualified","signed_complete",
]
RANK = {state: i for i, state in enumerate(MATURITY)}

EXPECTED_EPOCH_STATES = [
    "foreground_active","idle_eligible","baseline_freezing","mirror_gap_mining",
    "candidate_synthesis","adversarial_challenge","sandbox_experiment",
    "causal_evaluation","learning_consolidation","promotion_pending",
    "closed","preempted","quarantined","failed",
]

def validate_epoch(epoch: dict) -> list[str]:
    errors: list[str] = []
    if epoch.get("schema_version") != "skeleton.project_self_improvement_epoch.v1":
        errors.append("epoch: unexpected schema_version")
    if epoch.get("initial_state") != "foreground_active":
        errors.append("epoch: initial state must be foreground_active")
    if epoch.get("states") != EXPECTED_EPOCH_STATES:
        errors.append("epoch: state set/order changed")
    if epoch.get("terminal_states") != ["closed","preempted","quarantined","failed"]:
        errors.append("epoch: terminal states changed")

    transitions = epoch.get("transitions", [])
    expected_chain = [
        ("foreground_active","idle_eligible","idle_predicate_true"),
        ("idle_eligible","baseline_freezing","resource_budget_reserved_and_project_lock_nonexclusive"),
        ("baseline_freezing","mirror_gap_mining","immutable_baseline_receipt_written"),
        ("mirror_gap_mining","candidate_synthesis","prioritized_gap_set_nonempty"),
        ("candidate_synthesis","adversarial_challenge","candidate_set_nonempty"),
        ("adversarial_challenge","sandbox_experiment","at_least_one_candidate_survives_initial_challenge"),
        ("sandbox_experiment","causal_evaluation","bounded_experiment_receipts_complete"),
        ("causal_evaluation","learning_consolidation","baseline_candidate_comparison_complete"),
        ("learning_consolidation","promotion_pending","project_learning_receipt_written"),
        ("promotion_pending","closed","candidate_promoted_rejected_or_quarantined_and_epoch_receipt_written"),
    ]
    actual_chain = [(x.get("from"),x.get("to"),x.get("guard")) for x in transitions]
    if actual_chain != expected_chain:
        errors.append("epoch: deterministic happy-path transition chain changed")

    pre = epoch.get("global_preemption_transitions", {})
    active_states = EXPECTED_EPOCH_STATES[1:10]
    if pre.get("source_states") != active_states:
        errors.append("epoch: preemption must cover every active mirror-room state")
    if pre.get("to") != "preempted":
        errors.append("epoch: preemption target must be preempted")
    required_preemption_guards = {
        "foreground_instruction_arrived",
        "exclusive_project_mutation_requested",
        "mandatory_recovery_started",
        "safety_intervention_started",
        "protected_resource_reservation_violated",
    }
    if set(pre.get("guards", [])) != required_preemption_guards:
        errors.append("epoch: preemption guards changed")
    if "never partially promote" not in pre.get("action", ""):
        errors.append("epoch: preemption action must forbid partial promotion")

    idle = epoch.get("idle_predicate", {})
    required_idle_terms = {
        "foreground_runnable_queue_empty_or_external_blocked_only",
        "no_unresolved_foreground_instruction_waiting_for_execution",
        "no_exclusive_project_mutation_lock_owned",
        "no_mandatory_recovery_or_safety_intervention",
        "resource_budget_available_without_violating_foreground_reservations",
    }
    if set(idle.get("all", [])) != required_idle_terms:
        errors.append("epoch: idle predicate changed")
    if idle.get("false_on_unknown") is not True:
        errors.append("epoch: unknown idle state must fail closed")
    if "not to delay eligible work" not in idle.get("debounce", ""):
        errors.append("epoch: debounce may not delay eligible work")

    locks = epoch.get("locks", {})
    if locks.get("foreground_mutation_lock", {}).get("priority") != "absolute":
        errors.append("epoch: foreground mutation lock priority must be absolute")
    if locks.get("foreground_mutation_lock", {}).get("mirror_room_may_hold") is not False:
        errors.append("epoch: mirror room may not hold foreground mutation lock")
    if locks.get("candidate_namespace_lock", {}).get("production_write") is not False:
        errors.append("epoch: candidate namespace may not write production")

    budget = epoch.get("epoch_budget_schema", {})
    required_budgets = {
        "epoch_id","project_id","wall_clock_limit","experiment_limit","model_compute_limit",
        "cpu_limit","memory_limit","storage_limit","network_limit","external_api_limit",
    }
    if set(budget.get("required", [])) != required_budgets:
        errors.append("epoch: required resource budgets changed")
    if budget.get("carryover") != "none unless explicitly reauthorized by next epoch":
        errors.append("epoch: budget carryover must require explicit reauthorization")

    receipt_schemas = [
        "baseline_receipt_schema","hypothesis_schema","candidate_receipt_schema",
        "adversarial_receipt_schema","evaluation_receipt_schema","learning_receipt_schema",
        "promotion_receipt_schema","epoch_receipt_schema",
    ]
    for name in receipt_schemas:
        schema = epoch.get(name, {})
        if not schema.get("required"):
            errors.append(f"epoch: {name} missing required fields")

    promotion = epoch.get("promotion_receipt_schema", {})
    if set(promotion.get("forbidden_authority", [])) != {"proposer_room","challenger_room","verifier_room"}:
        errors.append("epoch: mirror rooms must remain forbidden promotion authorities")

    invariants = set(epoch.get("invariants", []))
    required_invariant_fragments = [
        "no transition may grant production authority",
        "foreground work always preempts mirror work",
        "partial promotion is forbidden",
        "negative results are durable project learning",
        "every epoch terminates before another epoch begins for the same project",
        "unknown idle state fails closed to foreground_active",
        "no project can satisfy another project's PSI-1000 maturity",
    ]
    for item in required_invariant_fragments:
        if item not in invariants:
            errors.append(f"epoch: missing invariant: {item}")
    return errors

def validate_scheduler(scheduler: dict) -> list[str]:
    errors: list[str] = []
    if scheduler.get("schema_version") != "skeleton.project_self_improvement_idle_scheduler.v1":
        errors.append("scheduler: unexpected schema_version")
    eligibility = scheduler.get("eligibility", {})
    if eligibility.get("unknown_state") != "ineligible":
        errors.append("scheduler: unknown eligibility must fail closed")
    if eligibility.get("production_mutation") != "forbidden":
        errors.append("scheduler: production mutation must remain forbidden")

    ranking = scheduler.get("ranking", {})
    hard_reject = set(ranking.get("hard_reject", []))
    for item in {
        "outside_project_scope","violates_non_compensable_invariant","cannot_be_sandboxed",
        "no_reproducible_baseline","no_rollback_or_compensation_path",
        "requires_production_in_place_mutation","budget_exceeds_available_idle_envelope",
    }:
        if item not in hard_reject:
            errors.append(f"scheduler: missing hard reject {item}")
    if "expected_capability_gain" not in ranking.get("maximize", []):
        errors.append("scheduler: capability gain must be maximized")
    if "expected_risk_reduction" not in ranking.get("maximize", []):
        errors.append("scheduler: risk reduction must be maximized")

    portfolio = scheduler.get("portfolio_policy", {})
    if not 0 < portfolio.get("exploration_share_floor", 0) <= 1:
        errors.append("scheduler: exploration share floor invalid")
    if not 0 < portfolio.get("exploit_share_ceiling", 0) <= 1:
        errors.append("scheduler: exploit share ceiling invalid")
    if portfolio.get("domain_starvation_limit_epochs", 0) <= 0:
        errors.append("scheduler: domain starvation limit required")
    if not portfolio.get("critical_regression_override"):
        errors.append("scheduler: critical regression override missing")

    plateau = scheduler.get("plateau_policy", {})
    if plateau.get("no_gain_threshold", 0) <= 0:
        errors.append("scheduler: no-gain threshold required")
    if plateau.get("repeated_failure_threshold", 0) <= plateau.get("no_gain_threshold", 0):
        errors.append("scheduler: repeated-failure threshold must exceed no-gain threshold")
    if "exponential backoff" not in plateau.get("action_after_no_gain", ""):
        errors.append("scheduler: no-gain action must back off")
    if "quarantine" not in plateau.get("action_after_repeated_failure", ""):
        errors.append("scheduler: repeated failures must quarantine")

    fairness = scheduler.get("project_fairness", {})
    if fairness.get("starvation_forbidden") is not True:
        errors.append("scheduler: eligible project starvation forbidden")
    if "deny-by-default" not in fairness.get("cross_project_evidence_use", ""):
        errors.append("scheduler: cross-project evidence use must deny by default")

    dispatch = scheduler.get("dispatch", {})
    for key in ("one_active_epoch_per_project","recheck_idle_before_dispatch","recheck_idle_before_experiment","recheck_idle_before_promotion","epoch_receipt_required_before_redispatch"):
        if dispatch.get(key) is not True:
            errors.append(f"scheduler: dispatch invariant {key} must be true")
    if dispatch.get("foreground_preemption") != "absolute":
        errors.append("scheduler: foreground preemption must be absolute")

    if not scheduler.get("audit_receipt", {}).get("required"):
        errors.append("scheduler: audit receipt schema missing")
    return errors

def validate(data: dict, epoch: dict | None = None, scheduler: dict | None = None) -> list[str]:
    errors: list[str] = []
    levels = data.get("levels", [])
    strata = data.get("strata", [])
    waves = data.get("construction_waves", [])
    rel = data.get("relationship", {})
    idle = data.get("idle_activation", {})
    mirror = data.get("mirror_room_topology", {})
    resources = data.get("resource_governance", {})
    candidates = data.get("candidate_policy", {})
    inst = data.get("project_instantiation", {})
    completion = data.get("completion", {})

    if data.get("schema_version") != "skeleton.project_self_improvement_1000.v1":
        errors.append("unexpected schema_version")
    if len(levels) != 1000:
        errors.append(f"expected 1000 levels, got {len(levels)}")
    if len(strata) != 100:
        errors.append(f"expected 100 strata, got {len(strata)}")
    if len(waves) != 100:
        errors.append(f"expected 100 construction waves, got {len(waves)}")

    if rel.get("expands_top_level_volumes") is not False:
        errors.append("PSI-1000 must not expand top-level volumes")
    if rel.get("frozen_volume_range") != ["VOL-000", "VOL-420"]:
        errors.append("frozen volume range changed")
    if rel.get("range") != ["PSI1000-0001", "PSI1000-1000"]:
        errors.append("unexpected PSI-1000 identity range")
    if rel.get("total_levels") != 1000 or rel.get("strata") != 100 or rel.get("levels_per_stratum") != 10:
        errors.append("relationship cardinality mismatch")

    expected = [f"PSI1000-{i:04d}" for i in range(1, 1001)]
    if [x.get("id") for x in levels] != expected:
        errors.append("level IDs/order must be exactly PSI1000-0001..PSI1000-1000")

    for i, layer in enumerate(levels, start=1):
        lid = layer.get("id")
        expected_stratum = f"PSI-S{((i - 1)//10)+1:03d}"
        if layer.get("ordinal") != i:
            errors.append(f"{lid}: ordinal mismatch")
        if layer.get("stratum_id") != expected_stratum:
            errors.append(f"{lid}: stratum mismatch")
        if layer.get("stage") != ((i - 1) % 10) + 1:
            errors.append(f"{lid}: stage mismatch")
        if layer.get("maturity") not in RANK:
            errors.append(f"{lid}: invalid maturity")
        if not layer.get("mirror_room_contract") or not layer.get("acceptance_proof"):
            errors.append(f"{lid}: missing mirror-room/proof contract")
        if layer.get("idle_eligible") is not True:
            errors.append(f"{lid}: must be idle eligible")
        if layer.get("foreground_preemptible") is not True:
            errors.append(f"{lid}: must be foreground preemptible")
        if layer.get("production_mutation_allowed") is not False:
            errors.append(f"{lid}: cannot permit direct production mutation")
        if layer.get("project_scoped") is not True:
            errors.append(f"{lid}: must be project scoped")
        expected_la = f"L400-{((i - 1) % 400) + 1:03d}"
        expected_aa = f"A400-{((i - 1) % 400) + 1:03d}"
        if layer.get("linked_learning_layer") != expected_la:
            errors.append(f"{lid}: learning link mismatch")
        if layer.get("linked_adversarial_layer") != expected_aa:
            errors.append(f"{lid}: adversarial link mismatch")
        for dep in layer.get("depends_on", []):
            if dep not in expected[:i-1]:
                errors.append(f"{lid}: dependency {dep} is unknown or not earlier")
        if layer.get("complete") is True:
            if layer.get("maturity") != "signed_complete":
                errors.append(f"{lid}: complete without signed_complete maturity")
            if not layer.get("implementation_signed"):
                errors.append(f"{lid}: complete without implementation signature")
            if not layer.get("independent_verification_signed"):
                errors.append(f"{lid}: complete without independent verification signature")
            if not layer.get("evidence"):
                errors.append(f"{lid}: complete without evidence")

    for i, s in enumerate(strata, start=1):
        sid = f"PSI-S{i:03d}"
        if s.get("id") != sid or s.get("ordinal") != i:
            errors.append(f"stratum {i}: identity mismatch")
        if s.get("layer_range") != [f"PSI1000-{((i-1)*10)+1:04d}", f"PSI1000-{i*10:04d}"]:
            errors.append(f"{sid}: range mismatch")

    for i, w in enumerate(waves, start=1):
        wid = f"PSI-W{i:03d}"
        if w.get("id") != wid:
            errors.append(f"wave {i}: identity mismatch")
        expected_prev = None if i == 1 else f"PSI-W{i-1:03d}"
        if w.get("prerequisite_wave") != expected_prev:
            errors.append(f"{wid}: prerequisite mismatch")

    if idle.get("semantics") != "foreground-idle, not machine-idle":
        errors.append("idle semantics changed")
    if idle.get("activation") != "immediate when deterministic idle predicate becomes true":
        errors.append("idle activation must remain immediate")
    if not idle.get("idle_predicate") or not idle.get("preemption"):
        errors.append("idle predicate/preemption missing")
    if not idle.get("continuous_idle_rule"):
        errors.append("continuous idle rule missing")
    if "debounce may prevent trigger flapping" not in idle.get("debounce_rule", ""):
        errors.append("idle debounce rule missing")

    for key in ["proposer_room","challenger_room","role_reversal","verifier_room","archivist_plane","isolation","finality"]:
        if not mirror.get(key):
            errors.append(f"mirror room topology missing {key}")

    if resources.get("foreground_priority") != "absolute":
        errors.append("foreground priority must be absolute")
    if resources.get("cancellation_required") is not True:
        errors.append("cancellation must be required")
    if resources.get("no_unbounded_loop") is not True:
        errors.append("unbounded mirror-room loops forbidden")
    if not resources.get("per_epoch_required_budgets"):
        errors.append("per-epoch budgets required")
    if "exponentially reduce frequency" not in resources.get("no_gain_backoff", ""):
        errors.append("no-gain backoff rule missing")

    if candidates.get("production_in_place_self_mutation") is not False:
        errors.append("production in-place self mutation must be false")
    if candidates.get("immutable_baseline_required") is not True:
        errors.append("immutable baseline required")
    if candidates.get("versioned_candidates_required") is not True:
        errors.append("versioned candidates required")
    if not candidates.get("promotion_requires"):
        errors.append("promotion requirements missing")

    if "independently for every project" not in inst.get("rule", ""):
        errors.append("per-project independent instantiation rule missing")
    if "deny-by-default" not in inst.get("cross_project_transfer", ""):
        errors.append("cross-project transfer must be deny-by-default")

    signed = sum(x.get("complete") is True for x in levels)
    if completion.get("template_levels") != 1000:
        errors.append("completion template level count mismatch")
    if completion.get("template_signed_complete") != signed:
        errors.append("template completion count mismatch")
    if completion.get("implementation_claim") is not False:
        errors.append("template must not claim implementation")
    if completion.get("global_project_qualification_claim") is not False:
        errors.append("template must not claim global project qualification")

    final = levels[-1] if levels else {}
    if final.get("id") != "PSI1000-1000":
        errors.append("finality identity must be PSI1000-1000")

    if epoch is not None:
        errors.extend(validate_epoch(epoch))
    if scheduler is not None:
        errors.extend(validate_scheduler(scheduler))
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=PATH)
    parser.add_argument("--epoch-path", type=Path, default=EPOCH_PATH)
    parser.add_argument("--scheduler-path", type=Path, default=SCHEDULER_PATH)
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    epoch = json.loads(args.epoch_path.read_text(encoding="utf-8"))
    scheduler = json.loads(args.scheduler_path.read_text(encoding="utf-8"))
    errors = validate(data, epoch, scheduler)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PSI-1000 valid: 1000 levels / 100 strata / deterministic preemptible mirror-room epochs + idle scheduler enforced")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
