#!/usr/bin/env python3
"""Validate derived NFR identities and optional measured threshold evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/nfr_registry.json")
ENGINEERING = Path("machine/ai_engineering_pass.json")
MASTER = Path("machine/ai_master_plan.json")


class NFRRegistryError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NFRRegistryError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise NFRRegistryError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise NFRRegistryError(f"{relative} must contain an object")
    return data


def _nfr_id(name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
    if not normalized:
        raise NFRRegistryError(f"invalid empty NFR budget class: {name!r}")
    return "NFR-" + normalized


def _number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise NFRRegistryError(f"{field} must be numeric")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise NFRRegistryError(f"{field} must be finite")
    return numeric


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    registry = _load(root, REGISTRY)
    engineering = _load(root, ENGINEERING)
    master = _load(root, MASTER)

    if registry.get("status") != "active":
        raise NFRRegistryError("NFR registry must be active")

    binding = registry.get("masterplan_binding")
    volume = next(
        (
            item
            for item in master.get("volumes", [])
            if isinstance(item, dict) and item.get("key") == "VOL-123"
        ),
        None,
    )
    if not isinstance(binding, dict) or not isinstance(volume, dict):
        raise NFRRegistryError("VOL-123 masterplan binding is required")
    if binding.get("title") != volume.get("title"):
        raise NFRRegistryError("NFR registry title drift from VOL-123")
    gaps = binding.get("required_gap_texts")
    if not isinstance(gaps, list) or not gaps:
        pass  # closed volume may have empty gap bindings
    for gap in gaps:
        if gap not in volume.get("gaps", []):
            raise NFRRegistryError(f"VOL-123 masterplan gap drift: {gap!r}")

    policy = registry.get("policy")
    if not isinstance(policy, dict):
        raise NFRRegistryError("NFR registry policy must be an object")
    budget_policy = engineering.get("budget_binding_policy")
    if not isinstance(budget_policy, dict):
        raise NFRRegistryError("engineering budget_binding_policy is required")
    if policy.get("no_invented_thresholds") is not True:
        raise NFRRegistryError("NFR registry must prohibit invented thresholds")
    if policy.get("binding_rule") != budget_policy.get("rule"):
        raise NFRRegistryError("NFR binding rule drift")
    if policy.get("production_rule") != budget_policy.get("production_rule"):
        raise NFRRegistryError("NFR production evidence rule drift")

    profiles = engineering.get("work_package_profiles")
    if not isinstance(profiles, list) or not profiles:
        raise NFRRegistryError("engineering work_package_profiles must be non-empty")

    expected: dict[str, dict[str, Any]] = {}
    expected_wp: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise NFRRegistryError("engineering work-package profile must be an object")
        wp = profile.get("id")
        if not isinstance(wp, str) or not wp:
            raise NFRRegistryError("engineering work package requires id")
        ids: list[str] = []
        for budget_class in profile.get("nfr_budget_classes", []):
            if not isinstance(budget_class, str) or not budget_class:
                raise NFRRegistryError(f"{wp} has invalid NFR budget class")
            nfr_id = _nfr_id(budget_class)
            ids.append(nfr_id)
            item = expected.setdefault(
                nfr_id,
                {
                    "nfr_id": nfr_id,
                    "budget_class": budget_class,
                    "work_package_refs": [],
                },
            )
            if item["budget_class"] != budget_class:
                raise NFRRegistryError(
                    f"NFR ID collision: {nfr_id} maps to multiple budget classes"
                )
            item["work_package_refs"].append(wp)
        expected_wp[wp] = {
            "work_package_ref": wp,
            "primary_wave": profile.get("primary_wave"),
            "engineering_class": profile.get("engineering_class"),
            "nfr_ids": sorted(ids),
            "evidence_modes": list(profile.get("evidence_modes", [])),
            "change_impact_triggers": list(profile.get("change_impact_triggers", [])),
            "recovery_requirements": list(profile.get("recovery_requirements", [])),
        }
    for item in expected.values():
        item["work_package_refs"].sort()

    actual_nfrs = registry.get("nfrs")
    if not isinstance(actual_nfrs, list):
        raise NFRRegistryError("nfrs must be a list")
    actual_by_id: dict[str, dict[str, Any]] = {}
    required_fields = list(budget_policy.get("required_fields", []))
    for item in actual_nfrs:
        if not isinstance(item, dict):
            raise NFRRegistryError("NFR entry must be an object")
        nfr_id = item.get("nfr_id")
        if not isinstance(nfr_id, str) or nfr_id in actual_by_id:
            raise NFRRegistryError(f"invalid/duplicate NFR id: {nfr_id!r}")
        actual_by_id[nfr_id] = item
        threshold = item.get("threshold_binding")
        if not isinstance(threshold, dict):
            raise NFRRegistryError(f"{nfr_id} threshold_binding must be an object")
        if threshold.get("status") != "required_before_promotion":
            raise NFRRegistryError(f"{nfr_id} threshold status drift")
        if threshold.get("required_fields") != required_fields:
            raise NFRRegistryError(f"{nfr_id} required threshold fields drift")
        if threshold.get("values") is not None:
            raise NFRRegistryError(
                f"{nfr_id} registry may not fabricate measured threshold values"
            )
        measurement = item.get("measurement_contract")
        if not isinstance(measurement, dict):
            raise NFRRegistryError(f"{nfr_id} measurement_contract must be an object")
        if measurement.get("harness") != "scripts/check_nfr_registry.py":
            raise NFRRegistryError(f"{nfr_id} measurement harness drift")
        if measurement.get("evidence_required") is not True:
            raise NFRRegistryError(f"{nfr_id} must require measurement evidence")
        if measurement.get("proof_rule") != budget_policy.get("production_rule"):
            raise NFRRegistryError(f"{nfr_id} measurement proof rule drift")

    if set(actual_by_id) != set(expected):
        missing = sorted(set(expected) - set(actual_by_id))
        extra = sorted(set(actual_by_id) - set(expected))
        raise NFRRegistryError(f"NFR coverage drift missing={missing} extra={extra}")
    for nfr_id, expected_item in expected.items():
        actual = actual_by_id[nfr_id]
        for field in ("nfr_id", "budget_class", "work_package_refs"):
            if actual.get(field) != expected_item[field]:
                raise NFRRegistryError(f"{nfr_id}.{field} drift")

    actual_wps = registry.get("work_package_bindings")
    if not isinstance(actual_wps, list):
        raise NFRRegistryError("work_package_bindings must be a list")
    actual_wp_by_id = {
        item.get("work_package_ref"): item
        for item in actual_wps
        if isinstance(item, dict)
    }
    if len(actual_wp_by_id) != len(actual_wps):
        raise NFRRegistryError("duplicate/malformed work-package NFR bindings")
    if set(actual_wp_by_id) != set(expected_wp):
        raise NFRRegistryError("work-package NFR coverage drift")
    for wp, expected_item in expected_wp.items():
        actual = actual_wp_by_id[wp]
        if actual != expected_item:
            raise NFRRegistryError(f"{wp} NFR binding drift")

    return {
        "status": "valid",
        "nfr_count": len(expected),
        "work_package_count": len(expected_wp),
        "masterplan_binding": "VOL-123",
        "required_measurement_fields": required_fields,
    }


def validate_measurements(
    root: Path,
    measurements_path: Path,
) -> dict[str, Any]:
    registry_result = validate(root)
    registry = _load(root, REGISTRY)
    data = _load(root, measurements_path)
    rows = data.get("measurements")
    if not isinstance(rows, list) or not rows:
        raise NFRRegistryError("measurements must be a non-empty list")

    known = {item["nfr_id"] for item in registry["nfrs"]}
    required_fields = set(registry_result["required_measurement_fields"])
    seen: set[str] = set()
    failed: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise NFRRegistryError("measurement row must be an object")
        nfr_id = row.get("nfr_id")
        if nfr_id not in known:
            raise NFRRegistryError(f"measurement references unknown NFR {nfr_id!r}")
        if nfr_id in seen:
            raise NFRRegistryError(f"duplicate NFR measurement: {nfr_id}")
        seen.add(nfr_id)

        binding = row.get("binding")
        if not isinstance(binding, dict):
            raise NFRRegistryError(f"{nfr_id} measurement binding must be an object")
        missing = sorted(required_fields - set(binding))
        if missing:
            raise NFRRegistryError(f"{nfr_id} measurement binding missing fields: {missing}")
        if any(binding.get(field) in (None, "") for field in required_fields):
            raise NFRRegistryError(f"{nfr_id} measurement binding has empty required fields")

        threshold = _number(binding.get("threshold"), f"{nfr_id}.threshold")
        measured = _number(row.get("measured_value"), f"{nfr_id}.measured_value")
        comparator = row.get("comparator")
        if comparator == "lte":
            passed = measured <= threshold
        elif comparator == "gte":
            passed = measured >= threshold
        else:
            raise NFRRegistryError(
                f"{nfr_id} comparator must be lte or gte"
            )
        declared = row.get("result")
        expected_result = "pass" if passed else "fail"
        if declared != expected_result:
            raise NFRRegistryError(
                f"{nfr_id} declared result {declared!r} does not match measurement"
            )
        if not passed:
            failed.append(nfr_id)

    if failed:
        raise NFRRegistryError(
            "non-compensable NFR threshold failures: " + ", ".join(sorted(failed))
        )

    return {
        **registry_result,
        "measurement_status": "valid",
        "measurement_count": len(rows),
        "measured_nfr_ids": sorted(seen),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--measurements")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    try:
        result = (
            validate_measurements(root, Path(args.measurements))
            if args.measurements
            else validate(root)
        )
    except NFRRegistryError as exc:
        print(f"NFR registry: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "NFR registry: OK "
            f"({result['nfr_count']} NFRs, "
            f"{result['work_package_count']} work packages)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
