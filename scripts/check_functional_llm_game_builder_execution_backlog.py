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
        if task.get("state") != "planned":
            fail(f"{task_id} may not be pre-completed")
        if task.get("implementation_signed") is not False:
            fail(f"{task_id} implementation signoff must remain false")
        if task.get("independent_verification_signed") is not False:
            fail(f"{task_id} verification signoff must remain false")

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
        if plane.get("state") != "planned":
            fail(f"{plane_id} may not be pre-completed")
        if plane.get("implementation_signed") is not False:
            fail(f"{plane_id} implementation signoff must remain false")
        if plane.get("independent_verification_signed") is not False:
            fail(f"{plane_id} verification signoff must remain false")

    print("FLGB execution backlog valid: 18 planes, 216 build units, zero pre-completed units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
