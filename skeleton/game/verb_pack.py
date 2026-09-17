"""Named verb laws. Table deltas. Fail-closed extract."""

from __future__ import annotations

from typing import Any

from skeleton.game.predicates import require_never_extracted


class VerbPackError(ValueError):
    pass


VERBS: dict[str, tuple[str, int, int]] = {
    "stoke": ("heat", 2, 0),
    "vent": ("heat", -2, 1),
    "wait": ("sleep", 1, 0),
    "sleep": ("sleep", 4, 1),
    "dream": ("sleep", -4, 1),
    "extract": ("extracted", 1, 1),
    "craft": ("parts", -1, 1),
    "barter": ("scrap", -1, 1),
    "pick": ("key", 1, 0),
    "unlock": ("locked", -1, 1),
    "bait": ("bait", -1, 1),
    "hide": ("alert", -2, 1),
    "sprint": ("alert", 2, 1),
    "listen": ("alert", 1, 0),
    "mark": ("alert", 3, 1),
    "calm": ("alert", -3, 1),
    "learn": ("xp", 2, 1),
    "forget": ("xp", -1, 0),
    "save": ("saved", 1, 1),
    "load": ("saved", 0, 1),
    "ascend": ("floor", 1, 1),
    "descend": ("floor", -1, 1),
    "jam": ("occupancy", 2, 1),
    "spill": ("occupancy", -2, 1),
    "fog": ("los_pen", 1, 0),
    "clearfog": ("los_pen", -1, 0),
    "coil": ("coil", 1, 1),
    "spendcoil": ("coil", -1, 1),
    "ward": ("heat", -1, 1),
    "bleed": ("hp", -2, 0),
    "mend": ("hp", 2, 1),
    "scare": ("threat", 2, 1),
    "soothe": ("threat", -2, 1),
    "quest": ("xp", 1, 1),
    "talk": ("xp", 0, 1),
    "seal": ("digest", 1, 1),
    "doctor": ("mass", 0, 1),
    "clip": ("mass", 0, 1),
    "warp": ("warp_count", 1, 1),
    "handoff": ("tokens", 1, 1),
}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VERBS:
        raise VerbPackError(name)
    stat, delta, cost = VERBS[name]
    nxt = dict(state)
    if cost and int(nxt.get("tokens", 8)) < cost:
        raise VerbPackError("tokens")
    if name == "extract":
        require_never_extracted(nxt)
        if int(nxt.get("heat", 0)) < 8:
            raise VerbPackError("cold")
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + delta)
    nxt["tokens"] = max(0, int(nxt.get("tokens", 8)) - cost)
    nxt["stored_prose"] = 0
    return nxt


def run(state: dict[str, Any], names: list[str]) -> dict[str, Any]:
    nxt = dict(state)
    for name in names:
        nxt = apply(nxt, name)
    nxt["stored_prose"] = 0
    return nxt
