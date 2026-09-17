"""Status pipeline. Named effects, apply + tick."""

from __future__ import annotations

from typing import Any


class StatusPipeError(ValueError):
    pass


MAX_STACK = 4
EFFECTS = {
    "poison": ("hp", -5, 3),
    "burn": ("hp", -8, 2),
    "freeze": ("stun", 1, 1),
    "stun": ("stun", 1, 1),
    "heatstroke": ("heat", 4, 2),
    "chill": ("heat", -3, 2),
    "bleed": ("hp", -3, 4),
    "regen": ("hp", 4, 3),
    "focus": ("atk", 2, 3),
    "weak": ("atk", -2, 3),
    "haste": ("spd", 1, 2),
    "slow": ("spd", -1, 2),
    "ward": ("def", 3, 2),
    "break": ("def", -3, 2),
    "dreamlock": ("dreams", 1, 1),
    "overheat": ("heat", 6, 1),
    "cooldown": ("heat", -6, 1),
    "alerted": ("alert", 1, 2),
    "hidden": ("alert", -1, 2),
    "marked": ("threat", 2, 3),
}


def apply_named(unit: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in EFFECTS:
        raise StatusPipeError(name)
    stat, delta, dur = EFFECTS[name]
    nxt = dict(unit)
    nxt[stat] = int(nxt.get(stat, 0)) + delta
    if stat in {"hp", "heat", "sleep"}:
        nxt[stat] = max(0, min(100, int(nxt[stat])))
    stacks = dict(nxt.get("status") or {})
    stacks[name] = min(MAX_STACK, int(stacks.get(name, 0)) + dur)
    nxt["status"] = stacks
    nxt["stored_prose"] = 0
    return nxt


def apply_poison(unit: dict[str, Any]) -> dict[str, Any]:
    return apply_named(unit, "poison")


def tick_all(unit: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(unit)
    stacks = dict(nxt.get("status") or {})
    for name in list(stacks):
        nxt = apply_named(nxt, name)
        stacks = dict(nxt.get("status") or {})
        left = int(stacks.get(name, 0)) - 1
        if left <= 0:
            stacks.pop(name, None)
        else:
            stacks[name] = left
        nxt["status"] = stacks
    nxt["stored_prose"] = 0
    return nxt


def card(unit: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "status_pipe", "status": dict(unit.get("status") or {}), "stored_prose": 0}
