#!/usr/bin/env python3
"""Validate competitive AI benchmark governance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/competitive_ai_benchmark_governance.json")
LADDER = Path("machine/competitive_ai_engineering_ladder.json")

class BenchmarkGovernanceError(RuntimeError):
    pass

def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkGovernanceError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BenchmarkGovernanceError(f"{path} must contain an object")
    return data

def _texts(value: Any, label: str, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise BenchmarkGovernanceError(f"{label} requires at least {minimum} entries")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise BenchmarkGovernanceError(f"{label} entries must be non-empty text")
    if len(value) != len(set(value)):
        raise BenchmarkGovernanceError(f"{label} entries must be unique")
    return value

def validate(root: Path = ROOT) -> dict[str, Any]:
    policy = _load(root / POLICY)
    ladder = _load(root / LADDER)

    if policy.get("schema_version") != "skeleton.competitive_ai_benchmark_governance.v1":
        raise BenchmarkGovernanceError("unsupported benchmark-governance schema")
    if policy.get("status") != "active_design_authority":
        raise BenchmarkGovernanceError("benchmark governance must be active_design_authority")

    prereg = policy.get("preregistration")
    if not isinstance(prereg, dict) or prereg.get("required") is not True:
        raise BenchmarkGovernanceError("benchmark preregistration must be mandatory")
    fields = set(_texts(prereg.get("required_fields"), "preregistration.required_fields", 18))
    for required in (
        "primary_outcome_metric","minimum_practical_effects",
        "protected_noninferiority_margins","multiple_comparison_method",
        "stopping_rule","independent_verifier_identity"
    ):
        if required not in fields:
            raise BenchmarkGovernanceError(f"missing preregistration field: {required}")

    rules = "\n".join(_texts(policy.get("anti_gaming_rules"), "anti_gaming_rules", 8)).lower()
    for fragment in ("primary outcomes", "failed slices", "replacement baseline", "generator self-grading", "negative"):
        if fragment not in rules:
            raise BenchmarkGovernanceError(f"missing anti-gaming rule: {fragment}")

    decision = policy.get("decision_rule")
    if not isinstance(decision, dict):
        raise BenchmarkGovernanceError("decision_rule must be an object")
    for field in ("primary_outcome","dominance_targets","preserved_properties","tails_and_saturation","multiplicity","evidence_retention"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            raise BenchmarkGovernanceError(f"decision_rule.{field} is required")

    state = policy.get("promotion_state_machine")
    if not isinstance(state, dict):
        raise BenchmarkGovernanceError("promotion_state_machine must be an object")
    expected_states = [
        "planned","implemented","hardened","benchmark_preregistered",
        "evaluation_complete","independently_verified","superior","stale","demoted"
    ]
    if state.get("states") != expected_states:
        raise BenchmarkGovernanceError("promotion states drifted")
    _texts(state.get("transitions"), "promotion_state_machine.transitions", 9)

    journeys = policy.get("cross_family_journeys")
    if not isinstance(journeys, list) or len(journeys) != 8:
        raise BenchmarkGovernanceError("exactly 8 cross-family journeys are required")
    ids = [row.get("id") for row in journeys]
    if ids != [f"CFQ-{i:02d}" for i in range(1, 9)]:
        raise BenchmarkGovernanceError("cross-family journey IDs must be CFQ-01..CFQ-08")
    valid_families = {row["id"] for row in ladder.get("families", []) if isinstance(row, dict) and isinstance(row.get("id"), str)}
    if valid_families != {f"F{i:02d}" for i in range(1, 21)}:
        raise BenchmarkGovernanceError("engineering ladder family authority is incomplete")
    covered: set[str] = set()
    for row in journeys:
        families = _texts(row.get("families"), f"{row.get('id')}.families", 3)
        if not set(families) <= valid_families:
            raise BenchmarkGovernanceError(f"{row.get('id')} references unknown family")
        _texts(row.get("must_prove"), f"{row.get('id')}.must_prove", 4)
        covered.update(families)

    if len(covered) < 18:
        raise BenchmarkGovernanceError("cross-family journeys cover too few engineering families")

    _texts(policy.get("evidence_bundle_required"), "evidence_bundle_required", 10)

    return {
        "status":"valid",
        "preregistration_fields":len(fields),
        "anti_gaming_rules":len(policy["anti_gaming_rules"]),
        "promotion_states":len(expected_states),
        "cross_family_journeys":len(journeys),
        "covered_families":len(covered),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT)
    except BenchmarkGovernanceError as exc:
        if args.json:
            print(json.dumps({"status":"invalid","error":str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else f"valid: {result}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
