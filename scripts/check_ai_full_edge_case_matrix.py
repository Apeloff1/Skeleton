#!/usr/bin/env python3
"""Validate complete W00-W30 edge/historical ownership and queue inheritance."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
FULL = ROOT / "machine" / "ai_full_edge_case_matrix.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
PRIORITY = ROOT / "machine" / "ai_edge_case_priority_queue.json"
HUMAN = ROOT / "docs" / "plan" / "FULL_EDGE_CASE_BUILD_MATRIX.md"

EXPECTED_PACKAGES = [f"WP-W{i:02d}" for i in range(31)]
VALID_CRITICALITY = {"critical", "high", "medium", "low", "reference"}


def validate() -> list[str]:
    errors: list[str] = []
    for path in (CATALOG, FULL, MASTER, QUEUE, PRIORITY, HUMAN):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matrix = json.loads(FULL.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    priority = json.loads(PRIORITY.read_text(encoding="utf-8"))

    catalog_entries = catalog.get("entries")
    packages = matrix.get("packages")
    if not isinstance(catalog_entries, list) or not catalog_entries:
        return ["catalog entries must be a non-empty list"]
    if not isinstance(packages, list):
        return ["full matrix packages must be a list"]

    catalog_by_id = {entry["id"]: entry for entry in catalog_entries}
    catalog_ids = set(catalog_by_id)
    package_ids = [pkg.get("id") for pkg in packages if isinstance(pkg, dict)]
    if package_ids != EXPECTED_PACKAGES:
        errors.append("full matrix must contain WP-W00 through WP-W30 exactly once and in order")
    if set(EXPECTED_PACKAGES) - set(master.get("p0_work_packages", [])):
        errors.append("master plan does not expose all W00-W30 packages")

    owner_map: dict[str, set[str]] = {entry_id: set() for entry_id in catalog_ids}
    for pkg in packages:
        pid = pkg.get("id", "?")
        refs = (
            pkg.get("historical_ids", [])
            + pkg.get("edge_case_ids", [])
            + pkg.get("obscure_ids", [])
        )
        if len(refs) != len(set(refs)):
            errors.append(f"{pid}: duplicate catalog references")
        unknown = set(refs) - catalog_ids
        if unknown:
            errors.append(f"{pid}: unknown catalog refs: {sorted(unknown)}")
        for ref in refs:
            owner_map.setdefault(ref, set()).add(pid)
        for field in ("exact_paths", "invariants", "test_targets", "acceptance"):
            values = pkg.get(field)
            if not isinstance(values, list) or not values:
                errors.append(f"{pid}: {field} must be non-empty")

    orphans = sorted(entry_id for entry_id, owners in owner_map.items() if not owners)
    if orphans:
        errors.append(f"orphan catalog entries: {orphans}")

    for entry_id, entry in catalog_by_id.items():
        crit = entry.get("criticality")
        if crit not in VALID_CRITICALITY:
            errors.append(f"{entry_id}: invalid criticality {crit!r}")
        modes = entry.get("recommended_test_modes")
        if not isinstance(modes, list) or not modes:
            errors.append(f"{entry_id}: recommended_test_modes must be non-empty")
        refs = entry.get("work_package_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{entry_id}: work_package_refs must be non-empty")
        else:
            if set(refs) != owner_map.get(entry_id, set()):
                errors.append(f"{entry_id}: catalog work_package_refs disagree with full matrix")
        if crit in {"critical", "high"} and entry.get("type") != "historical":
            if not set(modes or []) - {"design_review"}:
                errors.append(f"{entry_id}: critical/high concrete case lacks executable evidence mode")

    coverage = matrix.get("coverage", {})
    if coverage.get("catalog_total") != len(catalog_ids):
        errors.append("coverage.catalog_total is stale")
    if coverage.get("mapped_total") != len(catalog_ids):
        errors.append("coverage.mapped_total must equal full catalog size")
    if coverage.get("orphan_total") != 0:
        errors.append("coverage.orphan_total must equal zero")
    if coverage.get("work_packages") != 31:
        errors.append("coverage.work_packages must equal 31")

    expected_priority_ids = {
        entry_id
        for entry_id, entry in catalog_by_id.items()
        if entry.get("criticality") in {"critical", "high"}
    }
    priority_items = priority.get("items")
    if not isinstance(priority_items, list):
        errors.append("priority queue items must be a list")
    else:
        priority_ids = [item.get("id") for item in priority_items]
        if len(priority_ids) != len(set(priority_ids)):
            errors.append("priority queue contains duplicate ids")
        if set(priority_ids) != expected_priority_ids:
            errors.append("priority queue must contain every and only critical/high catalog case")
        for item in priority_items:
            entry = catalog_by_id.get(item.get("id"))
            if not entry:
                continue
            if item.get("criticality") != entry.get("criticality"):
                errors.append(f"{item.get('id')}: priority criticality disagrees with catalog")
            if set(item.get("work_package_refs", [])) != set(entry.get("work_package_refs", [])):
                errors.append(f"{item.get('id')}: priority owners disagree with catalog")
            if set(item.get("recommended_test_modes", [])) != set(entry.get("recommended_test_modes", [])):
                errors.append(f"{item.get('id')}: priority evidence modes disagree with catalog")
        counts = priority.get("counts", {})
        if counts.get("total") != len(expected_priority_ids):
            errors.append("priority counts.total is stale")
        if counts.get("P0") != sum(catalog_by_id[x]["criticality"] == "critical" for x in expected_priority_ids):
            errors.append("priority counts.P0 is stale")
        if counts.get("P1") != sum(catalog_by_id[x]["criticality"] == "high" for x in expected_priority_ids):
            errors.append("priority counts.P1 is stale")

    overlay = queue.get("acceptance_overlays", {}).get("full_program_edge_case_matrix", {})
    if overlay.get("contract") != "machine/ai_full_edge_case_matrix.json":
        errors.append("build queue missing full_program_edge_case_matrix overlay")

    valid_pkg_ids = set(package_ids)
    for task in queue.get("tasks", []):
        tid = task.get("task_id", "?")
        refs = task.get("work_package_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{tid}: missing work_package_refs")
            continue
        if set(refs) - valid_pkg_ids:
            errors.append(f"{tid}: work package refs outside full matrix")
        overlays = task.get("acceptance_overlays")
        if not isinstance(overlays, list) or "full_program_edge_case_matrix" not in overlays:
            errors.append(f"{tid}: missing full-program edge-case overlay")
        inherited: set[str] = set()
        for ref in refs:
            pkg = next((p for p in packages if p.get("id") == ref), None)
            if pkg:
                inherited.update(
                    pkg.get("historical_ids", [])
                    + pkg.get("edge_case_ids", [])
                    + pkg.get("obscure_ids", [])
                )
        stats = task.get("edge_case_inheritance")
        if not isinstance(stats, dict):
            errors.append(f"{tid}: missing edge_case_inheritance")
            continue
        if stats.get("catalog_total") != len(inherited):
            errors.append(f"{tid}: inherited catalog_total is stale")
        critical = sum(catalog_by_id[x].get("criticality") == "critical" for x in inherited)
        high = sum(catalog_by_id[x].get("criticality") == "high" for x in inherited)
        if stats.get("critical") != critical or stats.get("high") != high:
            errors.append(f"{tid}: inherited critical/high counts are stale")

    if HUMAN.is_file():
        text = HUMAN.read_text(encoding="utf-8")
        for marker in ("All **240** catalog entries", "W12–W30 construction overlays", "Hardening law"):
            if marker not in text:
                errors.append(f"human full matrix missing marker: {marker}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Full edge-case construction matrix: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    matrix = json.loads(FULL.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    priority = json.loads(PRIORITY.read_text(encoding="utf-8"))
    print(
        "Full edge-case construction matrix: OK "
        f"({matrix['coverage']['catalog_total']} catalog entries, "
        f"{matrix['coverage']['work_packages']} work packages, "
        f"{len(queue['tasks'])} queue tasks inheriting risk, "
        f"{priority['counts']['total']} prioritized critical/high cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
