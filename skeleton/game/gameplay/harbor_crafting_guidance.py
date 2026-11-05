"""Deterministic player guidance from actual legal gameplay transitions.

This is a one-turn legality preview, not a claim of optimal play or solvability.
No hint modifies a save, spends currency, or bypasses NPC collision checks.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, normalize_action,
    step, validate_source, verify_bundle,
)

SCHEMA = "skeleton.game.harbor.legal-actions.v1"
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 3
MAX_CANDIDATES = 64
FIELDS = {
    "schema", "bundle", "source_digest", "terminal_digest",
    "legal_actions", "report_digest",
}
PRIORITY = {
    "choose": 0, "deliver": 1, "craft": 2, "gather": 3,
    "trade": 4, "move": 5, "wait": 6,
}


def _candidates(source: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = [
        {"op": "choose", "choice": "signal"},
        {"op": "choose", "choice": "shelter"},
        {"op": "deliver"},
    ]
    actions.extend(
        {"op": "craft", "recipe": recipe["id"]}
        for recipe in source["recipes"]
    )
    actions.append({"op": "gather"})
    actions.extend(
        {"op": "trade", "item": item}
        for item in sorted(source["npc"]["stock"])
    )
    actions.extend(
        {"op": "move", "direction": direction}
        for direction in ("north", "south", "east", "west")
    )
    actions.append({"op": "wait"})
    if len(actions) > MAX_CANDIDATES:
        raise HarborError("guidance candidate budget exceeded")
    return actions


def legal_actions(source: Any, state: Any) -> list[dict[str, Any]]:
    """Enumerate exactly the transitions accepted by the canonical step."""
    world = validate_source(source)
    if not isinstance(state, dict):
        raise HarborError("invalid guidance state")
    if state.get("ending") is not None:
        return []
    if type(state.get("tick")) is not int:
        raise HarborError("invalid guidance tick")
    options: list[dict[str, Any]] = []
    for action in _candidates(world):
        try:
            normalized = normalize_action(action)
            updated = step(world, state, normalized)
        except HarborError:
            continue
        before_inventory = state["inventory"]
        after_inventory = updated["inventory"]
        delta = {
            item: after_inventory.get(item, 0) - before_inventory.get(item, 0)
            for item in sorted(set(before_inventory) | set(after_inventory))
            if after_inventory.get(item, 0) != before_inventory.get(item, 0)
        }
        options.append({
            "action": normalized,
            "next_tick": updated["tick"],
            "next_pos": list(updated["pos"]),
            "npc_pos": list(updated["npc_pos"]),
            "coins_delta": updated["coins"] - state["coins"],
            "inventory_delta": delta,
            "reputation_delta": updated["reputation"] - state["reputation"],
            "delivered": updated["delivered"],
            "ending": updated["ending"],
            "next_state_digest": digest(updated),
        })
    options.sort(key=lambda entry: (
        PRIORITY[entry["action"]["op"]],
        canonical(entry["action"]),
    ))
    return options


def legal_action_report(bundle: Any) -> dict[str, Any]:
    """Portable, replay-derived legal action list for CLI or game editors."""
    state = verify_bundle(bundle)
    result = {
        "schema": SCHEMA,
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "terminal_digest": bundle["terminal_digest"],
        "legal_actions": legal_actions(bundle["source"], state),
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_REPORT_BYTES:
        raise HarborError("guidance report exceeds byte limit")
    return result


def verify_legal_action_report(report: Any) -> list[dict[str, Any]]:
    """Reject forged legal moves, changed NPC availability or fabricated rewards."""
    _keys(report, FIELDS, "legal action report")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized guidance report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("guidance digest mismatch")
    rebuilt = legal_action_report(report["bundle"])
    if rebuilt != report:
        raise HarborError("guidance replay mismatch")
    return deepcopy(rebuilt["legal_actions"])
