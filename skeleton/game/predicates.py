"""State predicates. Fail-closed booleans for room/verb gates."""

from __future__ import annotations

from typing import Any


class PredicateError(ValueError):
    pass


CHECKS = {
    "has_heat": ("heat", ">=", 1),
    "hot": ("heat", ">=", 8),
    "overhot": ("heat", ">=", 12),
    "cold": ("heat", "<=", 2),
    "can_extract": ("heat", ">=", 8),
    "extracted_once": ("extracted", ">=", 1),
    "never_extracted": ("extracted", "==", 0),
    "has_scrap": ("scrap", ">=", 1),
    "has_parts": ("parts", ">=", 1),
    "has_key": ("key", ">=", 1),
    "locked": ("locked", "==", 1),
    "has_slept": ("slept", ">=", 1),
    "can_dream": ("sleep", ">=", 8),
    "alert": ("alert", ">=", 1),
    "threatened": ("threat", ">=", 2),
}


def _cmp(value: int, op: str, need: int) -> bool:
    if op == ">=":
        return value >= need
    if op == "<=":
        return value <= need
    if op == "==":
        return value == need
    raise PredicateError(op)


def eval_named(state: dict[str, Any], name: str) -> bool:
    if not isinstance(state, dict):
        raise PredicateError("state")
    if name not in CHECKS:
        raise PredicateError(name)
    stat, op, need = CHECKS[name]
    return _cmp(int(state.get(stat, 0)), op, need)


def is_hot(state: dict[str, Any]) -> bool:
    return eval_named(state, "hot")


def require_never_extracted(state: dict[str, Any]) -> dict[str, Any]:
    if not eval_named(state, "never_extracted"):
        raise PredicateError("never_extracted")
    return dict(state)


def gate(state: dict[str, Any], names: list[str]) -> bool:
    return all(eval_named(state, name) for name in names)
