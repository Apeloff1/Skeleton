#!/usr/bin/env python3
"""Validate the canonical P1 production-promotion execution map and task DAG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path("machine/ai_p1_execution_map.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")
BUILD_SEQUENCE_PATH = Path("machine/ai_master_build_sequence.json")
HUMAN_PATH = Path("docs/plan/P1_EXECUTION_MAP.md")
INDEX_PATH = Path("docs/plan/MASTER_INDEX.md")
MASTER_HUMAN_PATH = Path("docs/plan/MASTER_PLAN.md")

EXPECTED_P1_GAPS = {
    "gap-feedback-promotion",
    "gap-provider-redundancy",
    "gap-release-slo-loop",
}
EXPECTED_LANES = {
    "P1-L0",
    "P1-L1",
    "P1-L2",
    "P1-L3",
    "P1-L4",
    "P1-L5",
    "P1-L6",
    "P1-L7",
}
EXPECTED_PHASES = {
    "P1-PH0",
    "P1-PH1",
    "P1-PH2",
    "P1-PH3",
    "P1-PH4",
}
TERMINAL_LANE = "P1-L7"
TERMINAL_TASK = "P1-PROM-03"


class ValidationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path} must contain an object")
    return value


def _cycle_errors(
    graph: dict[str, set[str]],
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        marker = state.get(node, 0)
        if marker == 2:
            return
        if marker == 1:
            try:
                start = stack.index(node)
            except ValueError:
                start = 0
            cycle = stack[start:] + [node]
            errors.append(f"{label} dependency cycle: " + " -> ".join(cycle))
            return
        state[node] = 1
        stack.append(node)
        for dep in sorted(graph.get(node, set())):
            if dep in graph:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        visit(node)
    return errors


def _ancestor_set(
    graph: dict[str, set[str]],
    node: str,
) -> set[str]:
    found: set[str] = set()

    def walk(current: str) -> None:
        for dep in graph.get(current, set()):
            if dep in found:
                continue
            found.add(dep)
            walk(dep)

    walk(node)
    return found


def validate_repository(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    p1_map = _load(root / MAP_PATH)
    backlog = _load(root / BACKLOG_PATH)
    master = _load(root / MASTER_PLAN_PATH)
    construction = _load(root / CONSTRUCTION_PATH)
    sequence = _load(root / BUILD_SEQUENCE_PATH)

    for required_path in (HUMAN_PATH, INDEX_PATH, MASTER_HUMAN_PATH):
        if not (root / required_path).is_file():
            errors.append(f"missing P1 planning document: {required_path}")

    authority = master.get("authority")
    if not isinstance(authority, dict):
        errors.append("master plan authority must be an object")
    else:
        expected_authority = {
            "p1_execution_map": str(MAP_PATH),
            "p1_execution_map_human": str(HUMAN_PATH),
            "p1_task_backlog": str(BACKLOG_PATH),
        }
        for key, expected in expected_authority.items():
            if authority.get(key) != expected:
                errors.append(
                    f"master plan authority {key} must equal {expected}"
                )

    if (root / INDEX_PATH).is_file():
        index_text = (root / INDEX_PATH).read_text(encoding="utf-8")
        for marker in (
            "P1_EXECUTION_MAP.md",
            "ai_p1_execution_map.json",
            "ai_p1_task_backlog.json",
        ):
            if marker not in index_text:
                errors.append(f"master index missing P1 marker: {marker}")

    if (root / MASTER_HUMAN_PATH).is_file():
        master_text = (root / MASTER_HUMAN_PATH).read_text(encoding="utf-8")
        if "## 21.7 P1 trustworthy autonomous production map" not in master_text:
            errors.append("human master plan missing P1 maturity section")

    if p1_map.get("schema_version") != 1:
        errors.append("P1 execution map schema_version must be 1")
    if p1_map.get("status") != "active":
        errors.append("P1 execution map must be active")
    if backlog.get("schema_version") != 1:
        errors.append("P1 task backlog schema_version must be 1")
    if backlog.get("status") != "active":
        errors.append("P1 task backlog must be active")

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise ValidationError("master plan volumes must be a list")
    volume_by_ref = {
        str(item.get("key")): item
        for item in volumes
        if isinstance(item, dict) and item.get("key")
    }
    if len(volume_by_ref) != 421:
        errors.append(
            f"master plan volume count drift: expected 421, got {len(volume_by_ref)}"
        )
    breadth = master.get("breadth_freeze")
    if not isinstance(breadth, dict) or breadth.get("enabled") is not True:
        errors.append("master-plan breadth freeze must remain enabled")
    elif breadth.get("last_top_level_volume") != 420:
        errors.append("master-plan breadth freeze must remain at VOL-420")

    maturity = master.get("volume_maturity_policy")
    maturity_states = {
        str(key)
        for key, value in (maturity.items() if isinstance(maturity, dict) else [])
        if isinstance(value, dict) and "meaning" in value
    }

    gap_rows = construction.get("gap_register")
    if not isinstance(gap_rows, list):
        raise ValidationError("construction gap_register must be a list")
    p1_gap_rows = {
        str(item.get("id")): item
        for item in gap_rows
        if isinstance(item, dict) and item.get("priority") == "P1"
    }
    if set(p1_gap_rows) != EXPECTED_P1_GAPS:
        errors.append(
            "canonical P1 gap inventory drift: expected="
            + ",".join(sorted(EXPECTED_P1_GAPS))
            + " actual="
            + ",".join(sorted(p1_gap_rows))
        )
    for gap_id in sorted(EXPECTED_P1_GAPS):
        row = p1_gap_rows.get(gap_id)
        if row is None:
            continue
        if row.get("status") != "closed":
            errors.append(f"canonical P1 gap reopened: {gap_id}")
        outstanding = row.get("outstanding_evidence")
        if isinstance(outstanding, list) and outstanding:
            errors.append(f"canonical P1 gap has outstanding evidence: {gap_id}")

    baseline = p1_map.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("P1 execution map baseline must be an object")
    else:
        ids = baseline.get("canonical_p1_gap_ids")
        if not isinstance(ids, list) or set(ids) != EXPECTED_P1_GAPS:
            errors.append("P1 map baseline canonical gap list drift")
        if baseline.get("breadth_freeze_last_volume") != 420:
            errors.append("P1 map breadth-freeze baseline must be 420")
        if baseline.get("total_masterplan_volumes") != 421:
            errors.append("P1 map masterplan volume baseline must be 421")

    build_waves = sequence.get("waves")
    if not isinstance(build_waves, list):
        raise ValidationError("master build waves must be a list")
    wave_by_id = {
        str(item.get("id")): item
        for item in build_waves
        if isinstance(item, dict) and item.get("id")
    }

    lanes = p1_map.get("lanes")
    if not isinstance(lanes, list):
        raise ValidationError("P1 execution map lanes must be a list")
    lane_by_id = {
        str(item.get("id")): item
        for item in lanes
        if isinstance(item, dict) and item.get("id")
    }
    if set(lane_by_id) != EXPECTED_LANES:
        errors.append(
            "P1 lane inventory drift: expected="
            + ",".join(sorted(EXPECTED_LANES))
            + " actual="
            + ",".join(sorted(lane_by_id))
        )

    primary_owner: dict[str, str] = {}
    lane_volume_refs: dict[str, set[str]] = {}
    lane_graph: dict[str, set[str]] = {}
    all_primary: set[str] = set()

    for lane_id, lane in sorted(lane_by_id.items()):
        deps = lane.get("depends_on")
        if not isinstance(deps, list):
            errors.append(f"{lane_id}: depends_on must be a list")
            deps = []
        dep_set = {str(item) for item in deps}
        lane_graph[lane_id] = dep_set
        unknown_deps = dep_set - set(lane_by_id)
        if unknown_deps:
            errors.append(
                f"{lane_id}: unknown dependencies: {','.join(sorted(unknown_deps))}"
            )
        if lane_id in dep_set:
            errors.append(f"{lane_id}: lane cannot depend on itself")

        primary = lane.get("primary_volume_refs")
        if not isinstance(primary, list):
            errors.append(f"{lane_id}: primary_volume_refs must be a list")
            primary = []
        supporting = lane.get("supporting_volume_refs")
        if not isinstance(supporting, list):
            errors.append(f"{lane_id}: supporting_volume_refs must be a list")
            supporting = []

        lane_volume_refs[lane_id] = {
            str(item) for item in [*primary, *supporting]
        }

        for ref in primary:
            ref = str(ref)
            all_primary.add(ref)
            if ref not in volume_by_ref:
                errors.append(f"{lane_id}: unknown primary volume {ref}")
            prior = primary_owner.get(ref)
            if prior is not None and prior != lane_id:
                errors.append(
                    f"primary P1 volume has multiple owners: {ref} -> {prior},{lane_id}"
                )
            primary_owner[ref] = lane_id
        for ref in supporting:
            if str(ref) not in volume_by_ref:
                errors.append(f"{lane_id}: unknown supporting volume {ref}")

        target = lane.get("target_maturity")
        if target not in maturity_states:
            errors.append(f"{lane_id}: invalid target_maturity {target!r}")

        refs = lane.get("master_build_wave_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{lane_id}: master_build_wave_refs must be non-empty")
            refs = []
        referenced_packages: set[str] = set()
        for wave_ref in refs:
            wave = wave_by_id.get(str(wave_ref))
            if wave is None:
                errors.append(f"{lane_id}: unknown master build wave {wave_ref}")
                continue
            packages = wave.get("work_packages")
            if isinstance(packages, list):
                referenced_packages.update(str(item) for item in packages)

        declared_packages = lane.get("work_package_refs")
        if not isinstance(declared_packages, list) or not declared_packages:
            errors.append(f"{lane_id}: work_package_refs must be non-empty")
            declared_packages = []
        missing_packages = {
            str(item) for item in declared_packages
        } - referenced_packages
        if missing_packages:
            errors.append(
                f"{lane_id}: work packages not owned by referenced master waves: "
                + ",".join(sorted(missing_packages))
            )

        for field in (
            "objective",
            "implementation_slices",
            "acceptance",
            "stop_conditions",
            "required_evidence_modes",
            "fault_families",
            "quantitative_gates",
        ):
            value = lane.get(field)
            if isinstance(value, str):
                if not value.strip():
                    errors.append(f"{lane_id}: {field} must be non-empty")
            elif not isinstance(value, list) or not value:
                errors.append(f"{lane_id}: {field} must be non-empty")

    errors.extend(_cycle_errors(lane_graph, label="P1 lane"))

    phases = p1_map.get("phases")
    if not isinstance(phases, list):
        errors.append("P1 phases must be a list")
        phases = []
    phase_ids = {
        str(item.get("id"))
        for item in phases
        if isinstance(item, dict) and item.get("id")
    }
    if phase_ids != EXPECTED_PHASES:
        errors.append(
            "P1 phase inventory drift: expected="
            + ",".join(sorted(EXPECTED_PHASES))
            + " actual="
            + ",".join(sorted(phase_ids))
        )
    phase_lane_refs: list[str] = []
    expected_sequences = set(range(5))
    actual_sequences: set[int] = set()
    for phase in phases:
        if not isinstance(phase, dict):
            errors.append("P1 phase entries must be objects")
            continue
        pid = str(phase.get("id") or "?")
        sequence = phase.get("sequence")
        if isinstance(sequence, int):
            actual_sequences.add(sequence)
        else:
            errors.append(f"{pid}: sequence must be an integer")
        refs = phase.get("lane_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{pid}: lane_refs must be non-empty")
            refs = []
        for ref in refs:
            ref = str(ref)
            phase_lane_refs.append(ref)
            if ref not in lane_by_id:
                errors.append(f"{pid}: unknown lane ref {ref}")
        if not isinstance(phase.get("objective"), str) or not phase["objective"].strip():
            errors.append(f"{pid}: objective must be non-empty")
        exit_rules = phase.get("exit")
        if not isinstance(exit_rules, list) or not exit_rules:
            errors.append(f"{pid}: exit must be non-empty")
    if actual_sequences != expected_sequences:
        errors.append("P1 phase sequences must be exactly 0 through 4")
    if set(phase_lane_refs) != set(lane_by_id) or len(phase_lane_refs) != len(set(phase_lane_refs)):
        errors.append("P1 phases must cover every lane exactly once")
    terminal_phase = next(
        (item for item in phases if isinstance(item, dict) and item.get("id") == "P1-PH4"),
        None,
    )
    if not isinstance(terminal_phase, dict) or terminal_phase.get("lane_refs") != [TERMINAL_LANE]:
        errors.append("P1 terminal phase must contain only the terminal lane")

    terminal = lane_by_id.get(TERMINAL_LANE)
    if terminal is not None:
        if terminal.get("primary_volume_refs") != []:
            errors.append("terminal P1 lane must not own primary volumes")
        terminal_deps = {
            str(item) for item in terminal.get("depends_on", [])
        }
        expected_terminal_deps = EXPECTED_LANES - {TERMINAL_LANE}
        if terminal_deps != expected_terminal_deps:
            errors.append(
                "terminal P1 lane must depend on every non-terminal lane"
            )

    scope = p1_map.get("scope_summary")
    if not isinstance(scope, dict):
        errors.append("P1 scope_summary must be an object")
    else:
        primary_count = scope.get("primary_p1_frontier_volume_count")
        if primary_count != len(all_primary):
            errors.append(
                "P1 primary frontier count drift: "
                f"declared={primary_count} actual={len(all_primary)}"
            )
        deferred = scope.get("deferred_volume_count")
        expected_deferred = len(volume_by_ref) - len(all_primary)
        if deferred != expected_deferred:
            errors.append(
                "P1 deferred volume count drift: "
                f"declared={deferred} actual={expected_deferred}"
            )
        deferred_refs = scope.get("deferred_volume_refs")
        expected_deferred_refs = set(volume_by_ref) - all_primary
        if not isinstance(deferred_refs, list):
            errors.append("P1 deferred_volume_refs must be a list")
        elif set(str(item) for item in deferred_refs) != expected_deferred_refs:
            errors.append("P1 deferred_volume_refs must equal the exact non-primary volume complement")

    deferred_policy = p1_map.get("deferred_scope_policy")
    if not isinstance(deferred_policy, dict):
        errors.append("P1 deferred_scope_policy must be an object")
    else:
        if not isinstance(deferred_policy.get("rule"), str) or not deferred_policy["rule"].strip():
            errors.append("P1 deferred scope rule must be non-empty")
        groups = deferred_policy.get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append("P1 deferred scope groups must be non-empty")

    acceptance = p1_map.get("acceptance_program")
    if not isinstance(acceptance, dict):
        errors.append("P1 acceptance_program must be an object")
    else:
        if acceptance.get("exact_head_required") is not True:
            errors.append("P1 exact-head acceptance must be required")
        if acceptance.get("independent_verification_required") is not True:
            errors.append("P1 independent verification must be required")
        if acceptance.get("signed_accountability_required_for_maturity_promotion") is not True:
            errors.append("P1 signed accountability must gate maturity promotion")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise ValidationError("P1 task backlog tasks must be a list")
    task_by_id = {
        str(item.get("task_id")): item
        for item in tasks
        if isinstance(item, dict) and item.get("task_id")
    }
    if len(task_by_id) != len(tasks):
        errors.append("P1 task IDs must be unique and non-empty")

    status_values = backlog.get("status_values")
    allowed_status = (
        {str(item) for item in status_values}
        if isinstance(status_values, list)
        else set()
    )
    if not allowed_status:
        errors.append("P1 task backlog status_values must be non-empty")

    task_graph: dict[str, set[str]] = {}
    lane_task_counts = {lane_id: 0 for lane_id in lane_by_id}
    accountability_refs: set[str] = set()
    primary_task_refs: set[str] = set()

    for task_id, task in sorted(task_by_id.items()):
        lane_id = str(task.get("lane_id") or "")
        if lane_id not in lane_by_id:
            errors.append(f"{task_id}: unknown lane {lane_id!r}")
            allowed_volumes: set[str] = set()
        else:
            lane_task_counts[lane_id] += 1
            allowed_volumes = lane_volume_refs.get(lane_id, set())

        task_status = task.get("status")
        if task_status not in allowed_status:
            errors.append(f"{task_id}: invalid status {task_status!r}")

        refs = task.get("volume_refs")
        if not isinstance(refs, list):
            errors.append(f"{task_id}: volume_refs must be a list")
            refs = []
        for ref in refs:
            ref = str(ref)
            if ref not in volume_by_ref:
                errors.append(f"{task_id}: unknown volume {ref}")
            if ref in all_primary:
                primary_task_refs.add(ref)
            if lane_id in lane_by_id and ref not in allowed_volumes:
                errors.append(
                    f"{task_id}: volume {ref} is outside {lane_id} primary/supporting scope"
                )
        if lane_id == TERMINAL_LANE and refs:
            errors.append(f"{task_id}: terminal promotion tasks must not own volumes")

        deps = task.get("depends_on")
        if not isinstance(deps, list):
            errors.append(f"{task_id}: depends_on must be a list")
            deps = []
        dep_set = {str(item) for item in deps}
        task_graph[task_id] = dep_set
        unknown = dep_set - set(task_by_id)
        if unknown:
            errors.append(
                f"{task_id}: unknown task dependencies: {','.join(sorted(unknown))}"
            )
        if task_id in dep_set:
            errors.append(f"{task_id}: task cannot depend on itself")

        if not isinstance(task.get("objective"), str) or not task["objective"].strip():
            errors.append(f"{task_id}: objective must be non-empty")
        task_acceptance = task.get("acceptance")
        if not isinstance(task_acceptance, list) or len(task_acceptance) < 3:
            errors.append(f"{task_id}: acceptance must contain at least three checks")

        task_packages = task.get("work_package_refs")
        if not isinstance(task_packages, list) or not task_packages:
            errors.append(f"{task_id}: work_package_refs must be non-empty")
            task_packages = []
        lane_packages = set(
            str(item)
            for item in lane_by_id.get(lane_id, {}).get("work_package_refs", [])
        )
        if set(str(item) for item in task_packages) - lane_packages:
            errors.append(f"{task_id}: work_package_refs exceed lane ownership")

        for field in ("implementation_paths", "test_targets", "evidence_modes", "failure_modes"):
            value = task.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{task_id}: {field} must be non-empty")
        recovery = task.get("rollback_or_recovery")
        if not isinstance(recovery, str) or not recovery.strip():
            errors.append(f"{task_id}: rollback_or_recovery must be non-empty")
        if task.get("promotion_effect") not in {"maturity_candidate", "terminal_candidate"}:
            errors.append(f"{task_id}: invalid promotion_effect")

        accountability_ref = task.get("accountability_ref")
        if not isinstance(accountability_ref, str) or not accountability_ref:
            errors.append(f"{task_id}: accountability_ref must be non-empty")
        elif accountability_ref in accountability_refs:
            errors.append(
                f"{task_id}: duplicate accountability_ref {accountability_ref}"
            )
        else:
            accountability_refs.add(accountability_ref)

    errors.extend(_cycle_errors(task_graph, label="P1 task"))

    missing_primary_task_coverage = sorted(all_primary - primary_task_refs)
    if missing_primary_task_coverage:
        errors.append(
            "P1 primary volumes missing executable task coverage: "
            + ",".join(missing_primary_task_coverage)
        )

    tasks_by_lane: dict[str, set[str]] = {
        lane_id: {
            task_id
            for task_id, task in task_by_id.items()
            if task.get("lane_id") == lane_id
        }
        for lane_id in lane_by_id
    }
    for lane_id, lane in lane_by_id.items():
        for dep_lane in lane_graph.get(lane_id, set()):
            dep_tasks = tasks_by_lane.get(dep_lane, set())
            realized = any(
                bool(_ancestor_set(task_graph, task_id) & dep_tasks)
                for task_id in tasks_by_lane.get(lane_id, set())
            )
            if not realized:
                errors.append(
                    f"{lane_id}: lane dependency {dep_lane} is not realized in task DAG"
                )

    scheduling = backlog.get("scheduling_policy")
    initial_ready = (
        str(scheduling.get("initial_ready_task"))
        if isinstance(scheduling, dict)
        and scheduling.get("initial_ready_task")
        else ""
    )
    if initial_ready not in task_by_id:
        errors.append("P1 backlog initial_ready_task must reference a task")
    elif task_graph.get(initial_ready):
        errors.append("P1 backlog initial_ready_task must have no dependencies")

    for task_id, task in task_by_id.items():
        if task.get("status") not in {"ready", "in_progress"}:
            continue
        unmet = {
            dep
            for dep in task_graph.get(task_id, set())
            if task_by_id.get(dep, {}).get("status") != "done"
        }
        if task_id != initial_ready and unmet:
            errors.append(
                f"{task_id}: ready/in_progress with unmet dependencies: "
                + ",".join(sorted(unmet))
            )

    if TERMINAL_TASK not in task_by_id:
        errors.append(f"P1 task backlog missing terminal task {TERMINAL_TASK}")
    else:
        ancestors = _ancestor_set(task_graph, TERMINAL_TASK)
        orphaned = set(task_by_id) - ancestors - {TERMINAL_TASK}
        if orphaned:
            errors.append(
                "P1 tasks do not feed terminal promotion: "
                + ",".join(sorted(orphaned))
            )

    for lane_id, count in sorted(lane_task_counts.items()):
        if count == 0:
            errors.append(f"{lane_id}: lane has no P1 backlog tasks")

    declared_summary = backlog.get("summary")
    if not isinstance(declared_summary, dict):
        errors.append("P1 task backlog summary must be an object")
    else:
        if declared_summary.get("task_count") != len(task_by_id):
            errors.append("P1 task backlog task_count drift")
        actual_lane_counts = {
            lane_id: lane_task_counts[lane_id]
            for lane_id in sorted(lane_task_counts)
        }
        declared_lane_counts = declared_summary.get("lane_task_counts")
        if declared_lane_counts != actual_lane_counts:
            errors.append("P1 task backlog lane_task_counts drift")
        ready_count = sum(
            1 for task in task_by_id.values() if task.get("status") == "ready"
        )
        blocked_count = sum(
            1 for task in task_by_id.values() if task.get("status") == "blocked"
        )
        if declared_summary.get("ready_count") != ready_count:
            errors.append("P1 task backlog ready_count drift")
        if declared_summary.get("blocked_count") != blocked_count:
            errors.append("P1 task backlog blocked_count drift")
        for status_name in ("in_progress", "evidence_pending", "done"):
            actual = sum(
                1
                for task in task_by_id.values()
                if task.get("status") == status_name
            )
            if declared_summary.get(f"{status_name}_count") != actual:
                errors.append(f"P1 task backlog {status_name}_count drift")

    summary = {
        "ok": not errors,
        "lane_count": len(lane_by_id),
        "primary_volume_count": len(all_primary),
        "deferred_volume_count": len(volume_by_ref) - len(all_primary),
        "canonical_p1_gap_count": len(p1_gap_rows),
        "task_count": len(task_by_id),
        "ready_task_count": sum(
            1 for task in task_by_id.values() if task.get("status") == "ready"
        ),
        "terminal_lane": TERMINAL_LANE,
        "terminal_task": TERMINAL_TASK,
    }
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    try:
        errors, summary = validate_repository(ROOT)
    except ValidationError as exc:
        print(f"P1 execution map validation error: {exc}", file=sys.stderr)
        return 2

    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))

    if errors:
        print("P1 execution map: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "P1 execution map: OK "
        f"({summary['lane_count']} lanes; "
        f"{summary['primary_volume_count']} primary volumes; "
        f"{summary['task_count']} tasks; "
        f"{summary['deferred_volume_count']} deferred)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
