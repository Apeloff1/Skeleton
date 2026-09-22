#!/usr/bin/env python3
"""Validate the reverse-engineered end-state proof layer."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVERSE = ROOT / "machine" / "ai_reverse_engineering_pass.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
SEQUENCE = ROOT / "machine" / "ai_master_build_sequence.json"
ACCOUNTABILITY = ROOT / "machine" / "ai_build_accountability.json"
HUMAN = ROOT / "docs" / "plan" / "REVERSE_ENGINEERING_PASS.md"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"

EXPECTED_CHAINS = [f"REV-{i:02d}" for i in range(10)]
EXPECTED_CONSTRAINTS = [f"RC-{i:02d}" for i in range(1, 9)]

def validate() -> list[str]:
    errors: list[str] = []
    for path in (REVERSE, MASTER, SEQUENCE, ACCOUNTABILITY, HUMAN, INDEX, PLAN):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    reverse = json.loads(REVERSE.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    sequence = json.loads(SEQUENCE.read_text(encoding="utf-8"))

    if reverse.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    scope = reverse.get("scope_policy", {})
    if scope.get("breadth_frozen_at_volume") != 420:
        errors.append("reverse pass must preserve VOL-420 breadth freeze")
    if scope.get("adds_top_level_architecture") is not False:
        errors.append("reverse pass must not add top-level architecture")
    if scope.get("creates_completion_authority") is not False:
        errors.append("reverse pass must not create completion authority")
    if scope.get("completion_remains_derived_from_accountability") is not True:
        errors.append("completion must remain derived from signed accountability")

    chain_fields = set(reverse.get("required_chain_fields", []))
    expected_fields = {
        "id","terminal_outcome","acceptance_witnesses","required_wave_refs",
        "required_wp_refs","required_evidence_modes","failure_oracles",
        "forbidden_shortcuts","minimum_proof_bundle",
    }
    if chain_fields != expected_fields:
        errors.append("required_chain_fields drifted")

    waves = sequence.get("waves", [])
    wave_ids = {w.get("id") for w in waves}
    wp_ids = {wp for w in waves for wp in w.get("work_packages", [])}
    if wave_ids != {f"MBW-{i:02d}" for i in range(8)}:
        errors.append("build sequence wave set drifted")
    if wp_ids != {f"WP-W{i:02d}" for i in range(31)}:
        errors.append("build sequence work-package set drifted")

    chains = reverse.get("terminal_chains")
    if not isinstance(chains, list):
        return errors + ["terminal_chains must be a list"]
    ids = [c.get("id") for c in chains if isinstance(c, dict)]
    if ids != EXPECTED_CHAINS:
        errors.append("terminal chains must be REV-00 through REV-09 exactly once and in order")

    covered_waves: set[str] = set()
    for chain in chains:
        cid = chain.get("id", "?")
        for field in expected_fields - {"id"}:
            value = chain.get(field)
            if field == "terminal_outcome":
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{cid}: terminal_outcome must be non-empty")
            elif not isinstance(value, list) or not value:
                errors.append(f"{cid}: {field} must be a non-empty list")

        refs = chain.get("required_wave_refs", [])
        unknown_waves = [x for x in refs if x not in wave_ids]
        if unknown_waves:
            errors.append(f"{cid}: unknown wave refs {unknown_waves}")
        covered_waves.update(x for x in refs if x in wave_ids)

        wps = chain.get("required_wp_refs", [])
        unknown_wps = [x for x in wps if x not in wp_ids]
        if unknown_wps:
            errors.append(f"{cid}: unknown work-package refs {unknown_wps}")

        if not any(mode in {"negative_test","fault_injection","restart_test","rollback_test","adversarial","incident_drill","privacy_test","deletion_test"} for mode in chain.get("required_evidence_modes", [])):
            errors.append(f"{cid}: chain lacks negative/fault/restart/adversarial evidence mode")
        if len(chain.get("failure_oracles", [])) < 3:
            errors.append(f"{cid}: needs at least three failure oracles")
        if len(chain.get("forbidden_shortcuts", [])) < 3:
            errors.append(f"{cid}: needs at least three forbidden shortcuts")
        if "full_git_sha" not in chain.get("minimum_proof_bundle", []):
            errors.append(f"{cid}: minimum proof bundle must bind a full git SHA")
        if "independent_verification" not in chain.get("minimum_proof_bundle", []):
            errors.append(f"{cid}: minimum proof bundle must require independent verification")

    if covered_waves != wave_ids:
        errors.append(f"reverse terminal chains must cover every build wave; missing={sorted(wave_ids-covered_waves)}")

    constraints = reverse.get("global_reverse_constraints")
    if not isinstance(constraints, list):
        errors.append("global_reverse_constraints must be a list")
    else:
        cids = [c.get("id") for c in constraints if isinstance(c, dict)]
        if cids != EXPECTED_CONSTRAINTS:
            errors.append("reverse constraints must be RC-01 through RC-08 exactly once and in order")
        for constraint in constraints:
            if not constraint.get("name") or not constraint.get("rule"):
                errors.append(f"{constraint.get('id','?')}: constraint requires name and rule")

    if master.get("breadth_freeze", {}).get("last_top_level_volume") != 420:
        errors.append("master plan breadth freeze disagrees with reverse pass")
    if sequence.get("completion_semantics", {}).get("mode") != "derived_from_existing_accountability":
        errors.append("master build sequence completion semantics drifted")

    human = HUMAN.read_text(encoding="utf-8")
    for marker in (
        "Reverse-engineering laws",
        "Reverse terminal chains",
        "REV-00",
        "REV-09",
        "Cross-chain reverse constraints",
        "Assembly-order corrections derived by working backward",
        "Minimum proof bundles",
    ):
        if marker not in human:
            errors.append(f"human reverse pass missing marker: {marker}")

    index = INDEX.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    if "REVERSE_ENGINEERING_PASS.md" not in index or "ai_reverse_engineering_pass.json" not in index:
        errors.append("master index must link human and machine reverse pass")
    if "## 21.5 Reverse-engineered end-state proof graph" not in plan:
        errors.append("master plan must explain reverse-engineered end-state proof graph")

    return errors

def main() -> int:
    errors = validate()
    if errors:
        print("AI reverse-engineering pass: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    reverse = json.loads(REVERSE.read_text(encoding="utf-8"))
    print(
        "AI reverse-engineering pass: OK "
        f"({len(reverse['terminal_chains'])} terminal chains, "
        f"{len(reverse['global_reverse_constraints'])} reverse constraints, "
        "all MBW waves covered)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
