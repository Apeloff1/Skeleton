#!/usr/bin/env python3
"""Validate the canonical P1 production-promotion execution map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path("machine/ai_p1_execution_map.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")
BUILD_SEQUENCE_PATH = Path("machine/ai_master_build_sequence.json")

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
}
TERMINAL_LANE = "P1-L5"


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


def _cycle_errors(graph: dict[str, set[str]]) -> list[str]:
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
            errors.append("P1 lane dependency cycle: " + " -> ".join(cycle))
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


def validate_repository(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    p1_map = _load(root / MAP_PATH)
    master = _load(root / MASTER_PLAN_PATH)
    construction = _load(root / CONSTRUCTION_PATH)
    sequence = _load(root / BUILD_SEQUENCE_PATH)

    if p1_map.get("schema_version") != 1:
        errors.append("P1 execution map schema_version must be 1")
    if p1_map.get("status") != "active":
        errors.append("P1 execution map must be active")

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
    graph: dict[str, set[str]] = {}
    all_primary: set[str] = set()

    for lane_id, lane in sorted(lane_by_id.items()):
        deps = lane.get("depends_on")
        if not isinstance(deps, list):
            errors.append(f"{lane_id}: depends_on must be a list")
            deps = []
        dep_set = {str(item) for item in deps}
        graph[lane_id] = dep_set
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

        supporting = lane.get("supporting_volume_refs")
        if not isinstance(supporting, list):
            errors.append(f"{lane_id}: supporting_volume_refs must be a list")
            supporting = []
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
        ):
            value = lane.get(field)
            if isinstance(value, str):
                if not value.strip():
                    errors.append(f"{lane_id}: {field} must be non-empty")
            elif not isinstance(value, list) or not value:
                errors.append(f"{lane_id}: {field} must be non-empty")

    errors.extend(_cycle_errors(graph))

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

    summary = {
        "ok": not errors,
        "lane_count": len(lane_by_id),
        "primary_volume_count": len(all_primary),
        "deferred_volume_count": len(volume_by_ref) - len(all_primary),
        "canonical_p1_gap_count": len(p1_gap_rows),
        "terminal_lane": TERMINAL_LANE,
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
        f"{summary['deferred_volume_count']} deferred)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
