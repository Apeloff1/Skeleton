#!/usr/bin/env python3
"""Validate W00-W11 edge/historical construction obligations and queue binding."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "machine" / "ai_p0_edge_case_matrix.json"
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
BUILD_QUEUE = ROOT / "machine" / "ai_build_queue.json"
HUMAN = ROOT / "docs" / "plan" / "P0_EDGE_CASE_BUILD_MATRIX.md"

EXPECTED_PACKAGES = [f"WP-W{i:02d}" for i in range(12)]


def validate() -> list[str]:
    errors: list[str] = []
    for path in (MATRIX, CATALOG, MASTER, BUILD_QUEUE, HUMAN):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    build_queue = json.loads(BUILD_QUEUE.read_text(encoding="utf-8"))

    catalog_ids = {entry["id"] for entry in catalog["entries"]}
    master_wps = set(master.get("p0_work_packages", []))
    packages = matrix.get("packages")
    if not isinstance(packages, list):
        return ["packages must be a list"]

    ids = [pkg.get("id") for pkg in packages if isinstance(pkg, dict)]
    if ids != EXPECTED_PACKAGES:
        errors.append(f"packages must be exactly {EXPECTED_PACKAGES}")
    if not set(EXPECTED_PACKAGES) <= master_wps:
        errors.append("master plan does not expose every W00-W11 package")

    referenced: set[str] = set()
    for pkg in packages:
        pid = pkg.get("id", "?")
        for field in (
            "exact_paths",
            "historical_ids",
            "edge_case_ids",
            "obscure_ids",
            "invariants",
            "test_targets",
            "acceptance",
        ):
            values = pkg.get(field)
            if not isinstance(values, list) or not values:
                errors.append(f"{pid}: {field} must be a non-empty list")
        refs = (
            pkg.get("historical_ids", [])
            + pkg.get("edge_case_ids", [])
            + pkg.get("obscure_ids", [])
        )
        referenced.update(refs)
        unknown = sorted(set(refs) - catalog_ids)
        if unknown:
            errors.append(f"{pid}: unknown catalog ids: {unknown}")
        if len(set(refs)) != len(refs):
            errors.append(f"{pid}: duplicate catalog reference inside package")
        if len(pkg.get("invariants", [])) < 4:
            errors.append(f"{pid}: expected at least four invariants")
        if len(pkg.get("test_targets", [])) < 4:
            errors.append(f"{pid}: expected at least four test targets")
        if not all(isinstance(path, str) and path.strip() for path in pkg.get("exact_paths", [])):
            errors.append(f"{pid}: invalid exact path")
        if pkg.get("edge_coverage_status") not in matrix.get("status_values", []):
            errors.append(f"{pid}: invalid edge_coverage_status")

    if len(referenced) < 100:
        errors.append(
            f"W00-W11 should reference at least 100 unique catalog cases; found {len(referenced)}"
        )

    coverage = matrix.get("coverage", {})
    if coverage.get("unique_catalog_ids") != len(referenced):
        errors.append("coverage.unique_catalog_ids is stale")

    text = HUMAN.read_text(encoding="utf-8")
    for pid in EXPECTED_PACKAGES:
        if f"## {pid} " not in text:
            errors.append(f"human matrix missing section {pid}")

    overlay = (
        build_queue.get("acceptance_overlays", {})
        .get("p0_edge_case_matrix", {})
    )
    if overlay.get("contract") != "machine/ai_p0_edge_case_matrix.json":
        errors.append("build queue is not bound to machine/ai_p0_edge_case_matrix.json")

    tasks = build_queue.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("build queue tasks must be a non-empty list")
    else:
        for task in tasks:
            tid = task.get("task_id", "?")
            refs = task.get("work_package_refs")
            if not isinstance(refs, list) or not refs:
                errors.append(f"{tid}: missing work_package_refs")
                continue
            unknown_wps = sorted(set(refs) - master_wps)
            if unknown_wps:
                errors.append(f"{tid}: unknown work package refs: {unknown_wps}")
            if task.get("acceptance_overlay") != "p0_edge_case_matrix":
                errors.append(f"{tid}: missing p0_edge_case_matrix acceptance overlay")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("P0 edge-case construction matrix: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    build_queue = json.loads(BUILD_QUEUE.read_text(encoding="utf-8"))
    print(
        "P0 edge-case construction matrix: OK "
        f"({len(data['packages'])} work packages, "
        f"{data['coverage']['unique_catalog_ids']} unique catalog mappings, "
        f"{len(build_queue['tasks'])} queue tasks bound)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
