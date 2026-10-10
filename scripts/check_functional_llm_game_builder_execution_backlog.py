#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/functional_llm_game_builder_10mb_manifest.json"
BACKLOG = ROOT / "machine/functional_llm_game_builder_execution_backlog.json"


def fail(message: str) -> None:
    raise SystemExit("FLGB execution backlog invalid: " + message)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    backlog = json.loads(BACKLOG.read_text(encoding="utf-8"))

    if backlog.get("kind") != "functional-llm-game-builder-execution-backlog":
        fail("wrong kind")
    if backlog.get("plan_version") != manifest.get("plan_version"):
        fail("plan version drift")
    if backlog.get("completion_claim") is not False:
        fail("backlog cannot claim completion")

    planes = backlog.get("planes")
    tasks = backlog.get("tasks")
    if not isinstance(planes, list) or len(planes) != 18:
        fail("expected 18 planes")
    if not isinstance(tasks, list) or len(tasks) != 216:
        fail("expected 216 execution tasks")
    if backlog.get("plane_count") != 18 or backlog.get("task_count") != 216:
        fail("declared counts are stale")

    state_model = backlog.get("state_model")
    if not isinstance(state_model, dict):
        fail("state model missing")
    for required_state in (
        "planned",
        "implemented-pending-verification",
        "in-progress",
        "verified",
    ):
        if not isinstance(state_model.get(required_state), str) or not state_model[required_state].strip():
            fail(f"state model missing {required_state}")

    manifest_shards = manifest.get("shards", [])
    shard_by_id = {item["id"]: item for item in manifest_shards}
    if set(shard_by_id) != {f"FLGB-{i:02d}" for i in range(1, 19)}:
        fail("manifest plane set mismatch")

    plane_by_id = {plane.get("id"): plane for plane in planes}
    if set(plane_by_id) != set(shard_by_id):
        fail("backlog plane set mismatch")

    # Dependency graph must remain acyclic and final integration must depend on all peers.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(plane_id: str) -> None:
        if plane_id in visited:
            return
        if plane_id in visiting:
            fail(f"dependency cycle at {plane_id}")
        visiting.add(plane_id)
        plane = plane_by_id[plane_id]
        deps = plane.get("depends_on")
        if not isinstance(deps, list):
            fail(f"{plane_id} dependencies must be a list")
        for dep in deps:
            if dep not in plane_by_id:
                fail(f"{plane_id} references unknown dependency {dep}")
            visit(dep)
        visiting.remove(plane_id)
        visited.add(plane_id)

    for plane_id in plane_by_id:
        visit(plane_id)

    expected_final_deps = {f"FLGB-{i:02d}" for i in range(1, 18)}
    if set(plane_by_id["FLGB-18"].get("depends_on", [])) != expected_final_deps:
        fail("FLGB-18 must depend on all other planes")

    lifecycle = manifest["coverage"]["lifecycle"]
    evidence = manifest["coverage"]["proof_labels"]
    stress = manifest["coverage"]["stress_scenarios"]

    task_ids: set[str] = set()
    implementation_targets: set[str] = set()
    contract_targets: set[str] = set()
    test_targets: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    for task in tasks:
        task_id = task.get("id")
        plane_id = task.get("plane_id")
        subsystem = task.get("subsystem")
        if not isinstance(task_id, str) or task_id in task_ids:
            fail(f"invalid or duplicate task id {task_id!r}")
        task_ids.add(task_id)
        if plane_id not in plane_by_id:
            fail(f"{task_id} unknown plane")
        if subsystem not in shard_by_id[plane_id].get("subsystems", []):
            fail(f"{task_id} subsystem not registered by {plane_id}")
        pair = (plane_id, subsystem)
        if pair in seen_pairs:
            fail(f"duplicate plane/subsystem pair {pair}")
        seen_pairs.add(pair)

        plane = plane_by_id[plane_id]
        root = plane.get("implementation_root")
        implementation_target = task.get("implementation_target")
        contract_target = task.get("contract_target")
        test_target = task.get("test_target")
        if not isinstance(root, str) or not isinstance(implementation_target, str):
            fail(f"{task_id} missing implementation target")
        if not implementation_target.startswith(root.rstrip("/") + "/"):
            fail(f"{task_id} implementation target escapes plane root")
        if not isinstance(contract_target, str) or not contract_target.startswith(root.rstrip("/") + "/"):
            fail(f"{task_id} contract target escapes plane root")
        if not isinstance(test_target, str) or not test_target.startswith("tests/flgb/"):
            fail(f"{task_id} test target escapes FLGB test namespace")
        if implementation_target in implementation_targets:
            fail(f"duplicate implementation target {implementation_target}")
        if contract_target in contract_targets:
            fail(f"duplicate contract target {contract_target}")
        if test_target in test_targets:
            fail(f"duplicate test target {test_target}")
        implementation_targets.add(implementation_target)
        contract_targets.add(contract_target)
        test_targets.add(test_target)

        if task.get("required_lifecycle") != lifecycle:
            fail(f"{task_id} lifecycle drift")
        if task.get("required_evidence") != evidence:
            fail(f"{task_id} evidence drift")
        if task.get("required_stress") != stress:
            fail(f"{task_id} stress drift")
        gates = task.get("acceptance_gates")
        if not isinstance(gates, list) or len(gates) < 12:
            fail(f"{task_id} acceptance gate set incomplete")
        state = task.get("state")
        allowed_task_states = {
            "planned",
            "implemented-pending-verification",
            "verified",
        }
        if state not in allowed_task_states:
            fail(f"{task_id} invalid task state {state!r}")

        if state in {"implemented-pending-verification", "verified"}:
            for label, target in (
                ("implementation", implementation_target),
                ("contract", contract_target),
                ("test", test_target),
            ):
                target_path = ROOT / target
                if not target_path.is_file():
                    fail(f"{task_id} missing {label} target {target}")
                if target_path.stat().st_size <= 0:
                    fail(f"{task_id} empty {label} target {target}")
            try:
                contract_data = json.loads((ROOT / contract_target).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                fail(f"{task_id} contract target is not valid JSON: {exc}")
            if not isinstance(contract_data, dict) or contract_data.get("type") != "object":
                fail(f"{task_id} contract target is not an object schema")

        if state == "verified":
            if task.get("implementation_signed") is not True:
                fail(f"{task_id} verified state requires implementation signoff")
            if task.get("independent_verification_signed") is not True:
                fail(f"{task_id} verified state requires independent verification")
            evidence = task.get("verification_evidence")
            if not isinstance(evidence, dict):
                fail(f"{task_id} verified state requires evidence")
            for key in ("commit_sha", "workflow_run_id", "verified_at", "verifier"):
                if not isinstance(evidence.get(key), str) or not evidence[key].strip():
                    fail(f"{task_id} verified evidence missing {key}")
        else:
            if task.get("implementation_signed") is not False:
                fail(f"{task_id} unsigned state cannot claim implementation signoff")
            if task.get("independent_verification_signed") is not False:
                fail(f"{task_id} unsigned state cannot claim verification signoff")

    expected_pairs = {
        (shard["id"], subsystem)
        for shard in manifest_shards
        for subsystem in shard.get("subsystems", [])
    }
    if seen_pairs != expected_pairs:
        missing = sorted(expected_pairs - seen_pairs)[:10]
        extra = sorted(seen_pairs - expected_pairs)[:10]
        fail(f"plane/subsystem coverage mismatch missing={missing} extra={extra}")

    for plane_id, plane in plane_by_id.items():
        expected_task_ids = {
            task["id"] for task in tasks if task.get("plane_id") == plane_id
        }
        if set(plane.get("task_ids", [])) != expected_task_ids:
            fail(f"{plane_id} task index stale")
        if len(expected_task_ids) != 12:
            fail(f"{plane_id} must contain 12 build units")
        task_states = {
            task["state"] for task in tasks if task.get("plane_id") == plane_id
        }
        if task_states == {"planned"}:
            expected_plane_state = "planned"
        elif task_states == {"verified"}:
            expected_plane_state = "verified"
        elif task_states.issubset({"implemented-pending-verification", "verified"}) and (
            "implemented-pending-verification" in task_states
        ):
            expected_plane_state = "implemented-pending-verification"
        else:
            expected_plane_state = "in-progress"

        if plane.get("state") != expected_plane_state:
            fail(
                f"{plane_id} state drift: {plane.get('state')!r} != "
                f"{expected_plane_state!r}"
            )
        if expected_plane_state == "verified":
            if plane.get("implementation_signed") is not True:
                fail(f"{plane_id} verified state requires implementation signoff")
            if plane.get("independent_verification_signed") is not True:
                fail(f"{plane_id} verified state requires independent verification")
            for dependency in plane.get("depends_on", []):
                if plane_by_id[dependency].get("state") != "verified":
                    fail(f"{plane_id} verified before dependency {dependency}")
        else:
            if plane.get("implementation_signed") is not False:
                fail(f"{plane_id} unsigned state cannot claim implementation signoff")
            if plane.get("independent_verification_signed") is not False:
                fail(f"{plane_id} unsigned state cannot claim verification signoff")

    frontier_gate = backlog.get("frontier_competition_gate")
    if not isinstance(frontier_gate, dict):
        fail("frontier competition execution gate missing")
    if frontier_gate.get("authority") != (
        "machine/functional_llm_game_builder_10mb_manifest.json#frontier_competition"
    ):
        fail("frontier competition authority drift")
    if frontier_gate.get("status") != "planned-evidence-pending":
        fail("frontier competition execution status drift")
    if frontier_gate.get("completion_claim") is not False:
        fail("frontier competition execution gate cannot be pre-completed")
    if frontier_gate.get("required_task_ids") != ["FLGB-18-T11", "FLGB-18-T12"]:
        fail("frontier competition task fan-in drift")
    if not isinstance(frontier_gate.get("required_outputs"), list) or len(
        frontier_gate["required_outputs"]
    ) < 10:
        fail("frontier competition output bundle incomplete")
    if not isinstance(frontier_gate.get("non_compensable"), list) or len(
        frontier_gate["non_compensable"]
    ) < 5:
        fail("frontier competition non-compensable rules incomplete")
    if not isinstance(frontier_gate.get("core_targets"), list) or len(
        frontier_gate["core_targets"]
    ) != 3:
        fail("frontier competition core-target set drift")
    if frontier_gate.get("protocol_version") != "2.0":
        fail("frontier competition execution protocol version drift")
    measurement = frontier_gate.get("measurement_requirements")
    if not isinstance(measurement, dict):
        fail("frontier competition measurement requirements missing")
    if int(measurement.get("comparator_maximum_age_days", 999)) > 45:
        fail("frontier competition comparator freshness weakened")
    if int(measurement.get("minimum_independent_runs_per_scored_task", 0)) < 6:
        fail("frontier competition trial-count floor weakened")
    if float(measurement.get("confidence_interval_level", 0.0)) < 0.95:
        fail("frontier competition uncertainty floor weakened")
    if float(measurement.get("non_inferiority_margin_pp_max", 99.0)) > 2.0:
        fail("frontier competition non-inferiority margin weakened")
    if int(measurement.get("minimum_parity_or_better_domains", 0)) < 10:
        fail("frontier competition parity-domain floor weakened")
    if int(measurement.get("minimum_superior_core_targets", 0)) < 2:
        fail("frontier competition superior-core-target floor weakened")
    for key in (
        "equal_budget_head_to_head",
        "compute_normalized_pareto",
        "hidden_challenge_rotation",
        "anti_gaming_review",
        "long_horizon_50_and_80_percent_curves",
        "evaluator_independence",
    ):
        if measurement.get(key) is not True:
            fail(f"frontier competition measurement control disabled: {key}")
    for task_id in frontier_gate["required_task_ids"]:
        task = next((item for item in tasks if item.get("id") == task_id), None)
        if task is None:
            fail(f"frontier competition closure task missing: {task_id}")
        gates = task.get("acceptance_gates", [])
        for token in (
            "frontier registry",
            "12-domain frontier competition scorecard",
            "frontier parity-or-better",
            "blind human evaluation",
            "independently verified frontier challenge",
        ):
            if not any(token in str(gate) for gate in gates):
                fail(f"{task_id} missing frontier closure gate: {token}")
        closure = str(task.get("closure_rule", "")).lower()
        if "frontier protocol v2" not in closure:
            fail(f"{task_id} closure rule is not bound to frontier protocol v2")
        for token in (
            "six independent",
            "50%/80%",
            "compute-normalized",
            "anti-gaming",
            "evaluator independence",
            "statistical dominance",
        ):
            if token not in closure:
                fail(f"{task_id} frontier protocol v2 closure rule missing: {token}")

    print(
        "FLGB execution backlog valid: 18 planes, 216 build units, "
        "frontier competition fan-in bound, zero pre-completed units"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
