#!/usr/bin/env python3
"""Validate the canonical P0 AI closure-evidence ledger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "machine" / "ai_closure_evidence.json"
CONSTRUCTION = ROOT / "machine" / "ai_app_construction.json"

EXPECTED_CLOSURE_STATES = {
    "open",
    "ready_for_closure",
    "closed",
    "reopened",
}
EXPECTED_IMPLEMENTATION_STATES = {
    "planned",
    "architecture-detailed",
    "in_progress",
    "implemented",
    "complete",
}


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return data


def _strings(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )


def validate(
    ledger: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        ledger = _load(LEDGER) if ledger is None else ledger
        construction = _load(CONSTRUCTION) if construction is None else construction
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse closure-evidence inputs: {exc}"]

    if ledger.get("schema_version") != 1:
        errors.append("closure ledger schema_version must equal 1")
    if ledger.get("status") != "active":
        errors.append("closure ledger status must be active")
    if ledger.get("architecture_tag") != construction.get("architecture_tag"):
        errors.append("closure ledger architecture_tag drifted")
    if ledger.get("construction_version") != construction.get("construction_version"):
        errors.append("closure ledger construction_version drifted")
    if set(ledger.get("closure_states") or []) != EXPECTED_CLOSURE_STATES:
        errors.append("closure state inventory drifted")
    if set(ledger.get("implementation_states") or []) != EXPECTED_IMPLEMENTATION_STATES:
        errors.append("implementation state inventory drifted")

    pointer = construction.get("closure_evidence_ledger")
    if not isinstance(pointer, dict):
        errors.append("construction closure_evidence_ledger must be an object")
    else:
        expected_pointer = {
            "schema_version": 1,
            "status": "active",
            "ledger_version": ledger.get("ledger_version"),
            "path": "machine/ai_closure_evidence.json",
        }
        for key, expected in expected_pointer.items():
            if pointer.get(key) != expected:
                errors.append(f"construction closure_evidence_ledger.{key} drifted")

    gaps = construction.get("gap_register")
    closure = construction.get("functional_ai_closure")
    graph = construction.get("functional_ai_dependency_graph")
    if not isinstance(gaps, list):
        return errors + ["construction gap_register must be a list"]
    if not isinstance(closure, dict):
        return errors + ["construction functional_ai_closure must be an object"]
    if not isinstance(graph, dict):
        return errors + ["construction functional_ai_dependency_graph must be an object"]

    p0 = {
        gap.get("id"): gap
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("priority") == "P0"
        and isinstance(gap.get("id"), str)
    }
    required_p0 = set(closure.get("required_p0_gaps") or [])
    if required_p0 != set(p0):
        errors.append("functional_ai_closure required_p0_gaps disagrees with P0 gap register")

    node_by_gap = {
        node.get("gap"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("gap"), str)
    }
    blueprints = {
        item.get("gap"): item
        for item in closure.get("required_blueprints", [])
        if isinstance(item, dict) and isinstance(item.get("gap"), str)
    }

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return errors + ["closure ledger entries must be a list"]
    ids = [
        entry.get("gap")
        for entry in entries
        if isinstance(entry, dict)
    ]
    if len(ids) != len(entries) or any(not isinstance(gap, str) or not gap for gap in ids):
        errors.append("every closure entry requires a non-empty gap")
    if len(ids) != len(set(ids)):
        errors.append("closure ledger gaps must be unique")
    if set(ids) != set(p0):
        errors.append("closure ledger must cover every P0 gap exactly once")

    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("every closure ledger entry must be an object")
            continue
        gap_id = str(entry.get("gap") or "?")
        gap = p0.get(gap_id)
        node = node_by_gap.get(gap_id)
        blueprint_ref = blueprints.get(gap_id)
        if gap is None:
            errors.append(f"{gap_id}: unknown P0 gap")
            continue
        if node is None:
            errors.append(f"{gap_id}: missing functional dependency node")
        if blueprint_ref is None:
            errors.append(f"{gap_id}: missing required blueprint mapping")

        if entry.get("plane") != gap.get("plane"):
            errors.append(f"{gap_id}: plane disagrees with construction gap")
        if entry.get("gap_status") != gap.get("status"):
            errors.append(f"{gap_id}: gap_status disagrees with construction gap")
        if node is not None and entry.get("stage") != node.get("stage"):
            errors.append(f"{gap_id}: stage disagrees with functional dependency graph")

        impl_state = entry.get("implementation_state")
        if impl_state not in EXPECTED_IMPLEMENTATION_STATES:
            errors.append(f"{gap_id}: invalid implementation_state")
        decision = entry.get("closure_decision")
        if decision not in EXPECTED_CLOSURE_STATES:
            errors.append(f"{gap_id}: invalid closure_decision")

        if blueprint_ref is not None:
            key = blueprint_ref.get("key")
            blueprint = construction.get(key) if isinstance(key, str) else None
            if not isinstance(blueprint, dict):
                errors.append(f"{gap_id}: required blueprint is missing")
            elif impl_state != blueprint.get("status"):
                errors.append(f"{gap_id}: implementation_state disagrees with blueprint status")

        for field, allow_empty in (
            ("evidence_present", False),
            ("closure_evidence_required", False),
            ("outstanding_evidence", True),
            ("blockers", True),
            ("close_when", False),
            ("reopen_when", False),
        ):
            if not _strings(entry.get(field), allow_empty=allow_empty):
                errors.append(f"{gap_id}: {field} must be a unique string list")

        if decision == "closed":
            if entry.get("gap_status") != "closed":
                errors.append(f"{gap_id}: closed decision requires closed gap_status")
            if impl_state not in {"implemented", "complete"}:
                errors.append(f"{gap_id}: closed decision requires implemented/complete state")
            if entry.get("outstanding_evidence") != []:
                errors.append(f"{gap_id}: closed decision cannot retain outstanding evidence")
            if entry.get("blockers") != []:
                errors.append(f"{gap_id}: closed decision cannot retain blockers")
        elif decision == "ready_for_closure":
            if entry.get("outstanding_evidence") != [] or entry.get("blockers") != []:
                errors.append(f"{gap_id}: ready_for_closure cannot retain blockers/outstanding evidence")
        elif decision in {"open", "reopened"} and entry.get("gap_status") == "closed":
            errors.append(f"{gap_id}: open/reopened decision cannot claim closed gap_status")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI closure evidence: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = _load(LEDGER)
    print(f"AI closure evidence: OK ({len(data['entries'])} P0 gaps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
