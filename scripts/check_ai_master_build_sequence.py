#!/usr/bin/env python3
"""Validate the canonical master build sequence."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = ROOT / "machine" / "ai_master_build_sequence.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
PRIORITY = ROOT / "machine" / "ai_edge_case_priority_queue.json"
ACCOUNTABILITY = ROOT / "machine" / "ai_build_accountability.json"
HUMAN = ROOT / "docs" / "plan" / "MASTER_BUILD_SEQUENCE.md"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"

EXPECTED_WPS = [f"WP-W{i:02d}" for i in range(31)]
EXPECTED_WAVES = [f"MBW-{i:02d}" for i in range(8)]
EXPECTED_AIQ_STAGES = set(range(8))


def validate() -> list[str]:
    errors: list[str] = []
    for path in (SEQUENCE, MASTER, QUEUE, PRIORITY, ACCOUNTABILITY, HUMAN, INDEX, PLAN):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    seq = json.loads(SEQUENCE.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    priority = json.loads(PRIORITY.read_text(encoding="utf-8"))

    if seq.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if seq.get("scope_policy", {}).get("breadth_frozen_at_volume") != 420:
        errors.append("master build sequence must preserve breadth freeze at VOL-420")
    if seq.get("completion_semantics", {}).get("mode") != "derived_from_existing_accountability":
        errors.append("wave completion must derive from existing accountability")

    waves = seq.get("waves")
    if not isinstance(waves, list):
        return errors + ["waves must be a list"]
    ids = [w.get("id") for w in waves if isinstance(w, dict)]
    if ids != EXPECTED_WAVES:
        errors.append("waves must be MBW-00 through MBW-07 exactly once and in order")

    wp_owner: dict[str, str] = {}
    all_stage_refs: set[int] = set()
    id_set = set(ids)
    graph: dict[str, list[str]] = {}
    for wave in waves:
        wid = wave.get("id", "?")
        refs = wave.get("work_packages")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{wid}: work_packages must be non-empty")
            refs = []
        for ref in refs:
            if ref not in EXPECTED_WPS:
                errors.append(f"{wid}: unknown work package {ref}")
            if ref in wp_owner:
                errors.append(f"{ref}: multiple primary wave owners")
            wp_owner[ref] = wid

        stages = wave.get("aiq_stage_refs")
        if not isinstance(stages, list):
            errors.append(f"{wid}: aiq_stage_refs must be a list")
        else:
            all_stage_refs.update(x for x in stages if isinstance(x, int))

        deps = wave.get("hard_dependencies")
        if not isinstance(deps, list):
            errors.append(f"{wid}: hard_dependencies must be a list")
            deps = []
        if any(dep not in id_set for dep in deps):
            errors.append(f"{wid}: hard dependency references unknown wave")
        graph[wid] = deps

        for field in (
            "objective", "entry_criteria", "deliverables",
            "required_evidence_modes", "exit_criteria", "stop_conditions"
        ):
            value = wave.get(field)
            if field == "objective":
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{wid}: objective must be non-empty")
            elif not isinstance(value, list) or not value:
                errors.append(f"{wid}: {field} must be non-empty")

        forbidden = {"checkbox", "checkbox_mark", "completion_checkbox", "manual_complete"}
        if forbidden.intersection(wave):
            errors.append(f"{wid}: wave-local manual completion fields are forbidden")

    if set(wp_owner) != set(EXPECTED_WPS) or len(wp_owner) != len(EXPECTED_WPS):
        missing = [wp for wp in EXPECTED_WPS if wp not in wp_owner]
        extra = [wp for wp in wp_owner if wp not in EXPECTED_WPS]
        errors.append(f"work-package primary coverage mismatch; missing={missing}, extra={extra}")

    # dependency cycle detection
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(f"wave dependency cycle detected at {node}")
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in ids:
        visit(node)

    queue_stages = {task.get("stage") for task in queue.get("tasks", []) if isinstance(task.get("stage"), int)}
    if queue_stages != EXPECTED_AIQ_STAGES:
        errors.append("AIQ queue must expose stages 0 through 7")
    if not EXPECTED_AIQ_STAGES.issubset(all_stage_refs):
        errors.append("master build waves must reference every AIQ stage 0 through 7")

    # Every critical/high risk must resolve to at least one construction wave.
    for item in priority.get("items", []):
        owners = {
            wp_owner[wp] for wp in item.get("work_package_refs", [])
            if wp in wp_owner
        }
        if not owners:
            errors.append(f"{item.get('id', '?')}: critical/high risk has no build-wave owner")

    if master.get("breadth_freeze", {}).get("last_top_level_volume") != 420:
        errors.append("master plan breadth freeze disagrees with build sequence")
    if len(master.get("p0_work_packages", [])) != 31:
        errors.append("master plan must expose 31 work packages")
    if queue.get("accountability", {}).get("contract") != "machine/ai_build_accountability.json":
        errors.append("build queue accountability contract drifted")

    human = HUMAN.read_text(encoding="utf-8")
    for marker in (
        "canonical **middle layer**",
        "MBW-00 — Authority, Contracts & Semantic Bedrock",
        "MBW-07 — Installer, Distributed Runtime & Production Hardening",
        "Universal stop conditions",
        "Promotion evidence bundle",
    ):
        if marker not in human:
            errors.append(f"human build sequence missing marker: {marker}")

    index = INDEX.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    if "MASTER_BUILD_SEQUENCE.md" not in index or "ai_master_build_sequence.json" not in index:
        errors.append("master index must link human and machine build sequence")
    if "## 21.4 Master build sequence" not in plan:
        errors.append("master plan must explain master build sequence")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Master build sequence: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    seq = json.loads(SEQUENCE.read_text(encoding="utf-8"))
    print(
        "Master build sequence: OK "
        f"({len(seq['waves'])} waves, {len(EXPECTED_WPS)} work packages, "
        "AIQ stages 0-7 covered)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
