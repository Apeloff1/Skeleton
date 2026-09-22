#!/usr/bin/env python3
"""Validate the masterplan systems-engineering overlay.

Dependency-free and fail-closed. The engineering pass is a depth contract over
W00-W30, not a parallel completion or architecture system.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINEERING = ROOT / "machine" / "ai_engineering_pass.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
SEQUENCE = ROOT / "machine" / "ai_master_build_sequence.json"
HUMAN = ROOT / "docs" / "plan" / "ENGINEERING_PASS.md"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"

EXPECTED_WPS = [f"WP-W{i:02d}" for i in range(31)]
REQUIRED_DIMENSIONS = {
    "ENG-REQ", "ENG-IFACE", "ENG-STATE", "ENG-AUTH", "ENG-FAIL",
    "ENG-REC", "ENG-NFR", "ENG-CAP", "ENG-COMPAT", "ENG-OBS",
    "ENG-TEST", "ENG-EVAL", "ENG-REPRO", "ENG-DEPLOY", "ENG-OWN",
}
REQUIRED_PROFILE_FIELDS = (
    "id", "name", "primary_wave", "engineering_class",
    "required_dimensions", "primary_interfaces", "hard_invariants",
    "principal_failure_modes", "nfr_budget_classes", "evidence_modes",
    "change_impact_triggers", "recovery_requirements", "promotion_rule",
)


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} root must be an object")
    return data


def validate() -> list[str]:
    errors: list[str] = []
    for path in (ENGINEERING, MASTER, SEQUENCE, HUMAN, PLAN, INDEX):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    try:
        engineering = _load(ENGINEERING)
        master = _load(MASTER)
        sequence = _load(SEQUENCE)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse engineering inputs: {exc}"]

    if engineering.get("schema_version") != 1:
        errors.append("engineering schema_version must equal 1")
    if engineering.get("status") != "active":
        errors.append("engineering pass status must be active")
    breadth = engineering.get("breadth_policy", {})
    if breadth.get("adds_top_level_volumes") is not False:
        errors.append("engineering pass must not add top-level volumes")
    if breadth.get("last_top_level_volume") != 420:
        errors.append("engineering pass must preserve breadth freeze at VOL-420")
    if master.get("breadth_freeze", {}).get("last_top_level_volume") != 420:
        errors.append("master plan breadth freeze disagrees with engineering pass")

    dims = engineering.get("engineering_dimensions")
    if not isinstance(dims, list):
        errors.append("engineering_dimensions must be a list")
        dims = []
    dim_ids = [d.get("id") for d in dims if isinstance(d, dict)]
    if set(dim_ids) != REQUIRED_DIMENSIONS or len(dim_ids) != len(REQUIRED_DIMENSIONS):
        errors.append("engineering dimensions must contain the canonical 15 IDs exactly once")
    for dim in dims:
        if not isinstance(dim, dict):
            errors.append("every engineering dimension must be an object")
            continue
        if not str(dim.get("name", "")).strip() or not str(dim.get("rule", "")).strip():
            errors.append(f"{dim.get('id', '?')}: dimension name/rule must be non-empty")

    chain = engineering.get("closure_chain")
    required_chain = {
        "requirement", "interface", "state_and_invariant", "authority",
        "failure_model", "quantitative_budget", "implementation",
        "executable_test_or_eval", "fault_or_recovery_evidence", "telemetry",
        "migration_and_rollback", "reproducibility_record",
        "independent_verification", "signed_accountability",
    }
    if not isinstance(chain, list) or not required_chain.issubset(set(chain)):
        errors.append("closure_chain is incomplete")

    budget = engineering.get("budget_binding_policy", {})
    fields = budget.get("required_fields")
    if not isinstance(fields, list) or len(fields) < 9:
        errors.append("budget binding policy must define threshold metadata")
    if "measured values" not in str(budget.get("production_rule", "")):
        errors.append("production budget rule must require measured values")

    profiles = engineering.get("work_package_profiles")
    if not isinstance(profiles, list):
        errors.append("work_package_profiles must be a list")
        return errors
    ids = [p.get("id") for p in profiles if isinstance(p, dict)]
    if ids != EXPECTED_WPS:
        errors.append("engineering profiles must cover WP-W00..WP-W30 exactly once and in order")

    wave_owner: dict[str, str] = {}
    for wave in sequence.get("waves", []):
        if not isinstance(wave, dict):
            continue
        for wp in wave.get("work_packages", []):
            wave_owner[wp] = wave.get("id")

    known_dims = set(dim_ids)
    for profile in profiles:
        if not isinstance(profile, dict):
            errors.append("every engineering profile must be an object")
            continue
        pid = profile.get("id", "?")
        for field in REQUIRED_PROFILE_FIELDS:
            if field not in profile:
                errors.append(f"{pid}: missing {field}")
        if profile.get("primary_wave") != wave_owner.get(pid):
            errors.append(f"{pid}: primary_wave disagrees with master build sequence")
        pdims = profile.get("required_dimensions")
        if not isinstance(pdims, list) or not pdims:
            errors.append(f"{pid}: required_dimensions must be non-empty")
        elif any(d not in known_dims for d in pdims):
            errors.append(f"{pid}: unknown engineering dimension")
        for field in (
            "primary_interfaces", "hard_invariants", "principal_failure_modes",
            "nfr_budget_classes", "evidence_modes", "change_impact_triggers",
            "recovery_requirements",
        ):
            value = profile.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{pid}: {field} must be non-empty")
        if "No verified/hardened/production promotion" not in str(profile.get("promotion_rule", "")):
            errors.append(f"{pid}: promotion rule must fail closed")

    plan_ref = master.get("engineering_pass")
    if not isinstance(plan_ref, dict):
        errors.append("machine master plan must reference engineering_pass")
    else:
        if plan_ref.get("machine_contract") != "machine/ai_engineering_pass.json":
            errors.append("machine master plan engineering contract path drifted")
        if plan_ref.get("human_contract") != "docs/plan/ENGINEERING_PASS.md":
            errors.append("machine master plan engineering human path drifted")

    human = HUMAN.read_text(encoding="utf-8")
    for marker in (
        "Mandatory engineering dimensions",
        "Quantitative budget law",
        "Compatibility and migration law",
        "Failure and recovery law",
        "Engineering promotion gates",
        "Engineering stop conditions",
        "WP-W30 Production hardening",
    ):
        if marker not in human:
            errors.append(f"engineering document missing marker: {marker}")

    plan = PLAN.read_text(encoding="utf-8")
    for marker in (
        "## 21.5 Systems-engineering closure overlay",
        "machine/ai_engineering_pass.json",
        "docs/plan/ENGINEERING_PASS.md",
    ):
        if marker not in plan:
            errors.append(f"master plan missing engineering marker: {marker}")

    index = INDEX.read_text(encoding="utf-8")
    if "ENGINEERING_PASS.md" not in index or "ai_engineering_pass.json" not in index:
        errors.append("master index must link engineering human and machine contracts")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Masterplan engineering pass: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = _load(ENGINEERING)
    print(
        "Masterplan engineering pass: OK "
        f"({len(data['engineering_dimensions'])} dimensions, "
        f"{len(data['work_package_profiles'])} work packages)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
