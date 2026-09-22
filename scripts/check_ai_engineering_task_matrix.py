#!/usr/bin/env python3
"""Validate engineering and adversarial obligation propagation into AIQ tasks."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "machine" / "ai_engineering_task_matrix.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
ENGINEERING = ROOT / "machine" / "ai_engineering_pass.json"
ADVERSARIAL = ROOT / "machine" / "ai_adversarial_closure.json"
SEQUENCE = ROOT / "machine" / "ai_master_build_sequence.json"
HUMAN = ROOT / "docs" / "plan" / "ENGINEERING_TASK_MATRIX.md"
MASTER = ROOT / "machine" / "ai_master_plan.json"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"

ALLOWED_GATE_STATES = {
    "obligations_bound_evidence_pending",
    "evidence_partial",
    "evidence_complete",
}


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} root must be an object")
    return data


def _ordered_union(values: list[list[str]], order: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for seq in values:
        for value in seq:
            if value not in seen:
                seen.add(value)
                result.append(value)
    if order is None:
        return sorted(result)
    rank = {value: i for i, value in enumerate(order)}
    return sorted(result, key=lambda value: rank.get(value, len(rank)))


def validate() -> list[str]:
    errors: list[str] = []
    required_paths = (
        MATRIX, QUEUE, ENGINEERING, ADVERSARIAL, SEQUENCE,
        HUMAN, MASTER, PLAN, INDEX,
    )
    for path in required_paths:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    try:
        matrix = _load(MATRIX)
        queue = _load(QUEUE)
        engineering = _load(ENGINEERING)
        adversarial = _load(ADVERSARIAL)
        sequence = _load(SEQUENCE)
        master = _load(MASTER)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse engineering task inputs: {exc}"]

    if matrix.get("schema_version") != 1:
        errors.append("task engineering matrix schema_version must equal 1")
    if matrix.get("status") != "active":
        errors.append("task engineering matrix status must be active")
    if matrix.get("sources", {}).get("adversarial_closure") != "machine/ai_adversarial_closure.json":
        errors.append("task matrix must bind the adversarial closure source")

    profiles = engineering.get("work_package_profiles", [])
    profile_by = {
        p.get("id"): p
        for p in profiles
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    dim_order = [
        d.get("id")
        for d in engineering.get("engineering_dimensions", [])
        if isinstance(d, dict) and isinstance(d.get("id"), str)
    ]

    axes = adversarial.get("closure_axes", [])
    axis_by = {
        a.get("id"): a
        for a in axes
        if isinstance(a, dict) and isinstance(a.get("id"), str)
    }
    axis_order = [a.get("id") for a in axes if isinstance(a, dict)]
    wp_axis_coverage = adversarial.get("work_package_coverage", {})
    campaigns = adversarial.get("compound_campaigns", [])
    promotion_gate_ids = [
        g.get("id")
        for g in adversarial.get("promotion_gates", [])
        if isinstance(g, dict) and isinstance(g.get("id"), str)
    ]

    wave_by_wp: dict[str, str] = {}
    for wave in sequence.get("waves", []):
        if not isinstance(wave, dict):
            continue
        wid = wave.get("id")
        for wp in wave.get("work_packages", []):
            if isinstance(wid, str) and isinstance(wp, str):
                wave_by_wp[wp] = wid

    queue_tasks = queue.get("tasks")
    matrix_tasks = matrix.get("tasks")
    if not isinstance(queue_tasks, list) or not isinstance(matrix_tasks, list):
        return errors + ["queue and matrix tasks must both be lists"]

    queue_ids = [t.get("task_id") for t in queue_tasks if isinstance(t, dict)]
    matrix_ids = [t.get("task_id") for t in matrix_tasks if isinstance(t, dict)]
    if matrix_ids != queue_ids:
        errors.append("engineering task matrix must cover AIQ tasks exactly once and in queue order")

    matrix_by = {
        t.get("task_id"): t
        for t in matrix_tasks
        if isinstance(t, dict) and isinstance(t.get("task_id"), str)
    }

    overlays = queue.get("acceptance_overlays", {})
    engineering_overlay = overlays.get("engineering_task_matrix")
    adversarial_overlay = overlays.get("adversarial_closure")
    if not isinstance(engineering_overlay, dict):
        errors.append("build queue must declare engineering_task_matrix acceptance overlay")
    else:
        if engineering_overlay.get("contract") != "machine/ai_engineering_task_matrix.json":
            errors.append("engineering task overlay contract path drifted")
    if not isinstance(adversarial_overlay, dict):
        errors.append("build queue must declare adversarial_closure acceptance overlay")
    else:
        if adversarial_overlay.get("contract") != "machine/ai_adversarial_closure.json":
            errors.append("adversarial closure overlay contract path drifted")

    for task in queue_tasks:
        if not isinstance(task, dict):
            errors.append("every queue task must be an object")
            continue
        tid = task.get("task_id", "?")
        row = matrix_by.get(tid)
        if not isinstance(row, dict):
            errors.append(f"{tid}: missing engineering matrix row")
            continue

        wp_refs = task.get("work_package_refs")
        if not isinstance(wp_refs, list) or not wp_refs:
            errors.append(f"{tid}: work_package_refs must be non-empty")
            continue
        unknown = [wp for wp in wp_refs if wp not in profile_by]
        if unknown:
            errors.append(f"{tid}: unknown engineering profiles {unknown}")
            continue

        referenced_profiles = [profile_by[wp] for wp in wp_refs]
        expected_dims = _ordered_union(
            [p.get("required_dimensions", []) for p in referenced_profiles],
            dim_order,
        )
        expected_budgets = _ordered_union(
            [p.get("nfr_budget_classes", []) for p in referenced_profiles]
        )
        expected_evidence = _ordered_union(
            [p.get("evidence_modes", []) for p in referenced_profiles]
        )
        expected_failures = _ordered_union(
            [p.get("principal_failure_modes", []) for p in referenced_profiles]
        )
        expected_recovery = _ordered_union(
            [p.get("recovery_requirements", []) for p in referenced_profiles]
        )
        expected_triggers = _ordered_union(
            [p.get("change_impact_triggers", []) for p in referenced_profiles]
        )
        expected_waves = sorted({wave_by_wp[wp] for wp in wp_refs if wp in wave_by_wp})

        expected_axes = _ordered_union(
            [wp_axis_coverage.get(wp, []) for wp in wp_refs],
            axis_order,
        )
        expected_adv_evidence = _ordered_union(
            [
                axis_by[axis_id].get("required_evidence_modes", [])
                for axis_id in expected_axes
                if axis_id in axis_by
            ]
        )
        expected_stop_conditions = [
            f"{axis_id}: {axis_by[axis_id].get('stop_condition', '')}"
            for axis_id in expected_axes
            if axis_id in axis_by
        ]
        expected_campaigns = [
            campaign.get("id")
            for campaign in campaigns
            if isinstance(campaign, dict)
            and isinstance(campaign.get("id"), str)
            and any(wp in wp_refs for wp in campaign.get("work_packages", []))
        ]

        exact_fields = {
            "engineering_profile_refs": wp_refs,
            "construction_wave_refs": expected_waves,
            "required_dimensions": expected_dims,
            "nfr_budget_classes": expected_budgets,
            "evidence_modes": expected_evidence,
            "principal_failure_modes": expected_failures,
            "recovery_requirements": expected_recovery,
            "change_impact_triggers": expected_triggers,
            "adversarial_closure_axis_refs": expected_axes,
            "adversarial_evidence_modes": expected_adv_evidence,
            "adversarial_stop_conditions": expected_stop_conditions,
            "compound_campaign_refs": expected_campaigns,
            "adversarial_promotion_gate_refs": promotion_gate_ids,
        }
        for field, expected in exact_fields.items():
            actual = row.get(field)
            if actual != expected:
                errors.append(f"{tid}: {field} does not equal inherited union")

        if row.get("stage") != task.get("stage"):
            errors.append(f"{tid}: stage drift between queue and engineering matrix")
        if row.get("accountability_id") != task.get("accountability_id"):
            errors.append(f"{tid}: accountability id drift")

        task_overlays = task.get("acceptance_overlays", [])
        for required_overlay in ("engineering_task_matrix", "adversarial_closure"):
            if required_overlay not in task_overlays:
                errors.append(f"{tid}: queue task does not enable {required_overlay} overlay")

        inheritance = task.get("engineering_inheritance")
        if not isinstance(inheritance, dict):
            errors.append(f"{tid}: missing engineering_inheritance")
        else:
            if inheritance.get("source") != "machine/ai_engineering_task_matrix.json":
                errors.append(f"{tid}: engineering inheritance source drift")
            if inheritance.get("engineering_profile_refs") != wp_refs:
                errors.append(f"{tid}: engineering inheritance profiles drift")
            if inheritance.get("adversarial_closure_source") != "machine/ai_adversarial_closure.json":
                errors.append(f"{tid}: adversarial inheritance source drift")

        gate = row.get("engineering_gate_state")
        if gate not in ALLOWED_GATE_STATES:
            errors.append(f"{tid}: invalid engineering_gate_state")
        evidence_refs = row.get("engineering_evidence_refs")
        budget_refs = row.get("budget_binding_refs")
        adv_refs = row.get("adversarial_evidence_refs")
        if not isinstance(evidence_refs, list) or not isinstance(budget_refs, list) or not isinstance(adv_refs, list):
            errors.append(f"{tid}: engineering/adversarial evidence refs must be lists")
        elif gate == "evidence_complete" and (not evidence_refs or not budget_refs or not adv_refs):
            errors.append(f"{tid}: evidence_complete requires engineering, budget and adversarial bindings")
        elif gate == "obligations_bound_evidence_pending" and (evidence_refs or budget_refs or adv_refs):
            errors.append(f"{tid}: pending gate must not claim evidence or budget bindings")

    task_propagation = engineering.get("task_propagation")
    if not isinstance(task_propagation, dict):
        errors.append("engineering pass must declare task_propagation")
    else:
        if task_propagation.get("machine_contract") != "machine/ai_engineering_task_matrix.json":
            errors.append("engineering task propagation machine path drifted")

    master_task = master.get("engineering_pass", {}).get("task_matrix")
    if master_task != "machine/ai_engineering_task_matrix.json":
        errors.append("master plan must link engineering task matrix")

    human = HUMAN.read_text(encoding="utf-8")
    for marker in (
        "Mandatory propagation rules",
        "Task ledger",
        "Required implementation packet",
        "Fail-closed rules",
        "Adversarial source",
    ):
        if marker not in human:
            errors.append(f"engineering task document missing marker: {marker}")

    plan_text = PLAN.read_text(encoding="utf-8")
    if "## 21.7 Atomic task engineering propagation" not in plan_text:
        errors.append("master plan must explain atomic task engineering propagation")
    index_text = INDEX.read_text(encoding="utf-8")
    if "ENGINEERING_TASK_MATRIX.md" not in index_text or "ai_engineering_task_matrix.json" not in index_text:
        errors.append("master index must link engineering task matrix contracts")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AIQ engineering/adversarial propagation: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = _load(MATRIX)
    print(f"AIQ engineering/adversarial propagation: OK ({len(data['tasks'])} atomic tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
