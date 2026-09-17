"""Wave-4 extra verbs."""

from __future__ import annotations

from typing import Any


class VerbWaveError(ValueError):
    pass


VERBS: dict[str, tuple[str, int, int]] = {
    "peek": ("alert", 1, 0), "probe": ("alert", 1, 1), "brace": ("hp", 1, 1),
    "duck": ("alert", -1, 0), "climb": ("floor", 1, 1), "drop": ("floor", -1, 1),
    "toss": ("bait", -1, 1), "catch": ("scrap", 1, 0), "bind": ("locked", 1, 1),
    "cut": ("hp", -1, 1), "stitch": ("hp", 1, 1), "smear": ("heat", 1, 0),
    "wipe": ("heat", -1, 0), "tap": ("alert", 0, 0), "knock": ("alert", 1, 0),
    "shove": ("alert", 2, 1), "yield": ("alert", -2, 0), "hold": ("alert", 0, 1),
    "aim": ("alert", 1, 1), "feint": ("alert", 1, 1), "flank": ("alert", 2, 1),
    "cover": ("alert", -1, 1), "signal": ("tokens", -1, 0), "recall": ("xp", 1, 1),
}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VERBS:
        raise VerbWaveError(name)
    stat, delta, cost = VERBS[name]
    nxt = dict(state)
    if cost and int(nxt.get("tokens", 8)) < cost:
        raise VerbWaveError("tokens")
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + delta)
    nxt["tokens"] = max(0, int(nxt.get("tokens", 8)) - cost)
    nxt["last_verb"] = name
    nxt["stored_prose"] = 0
    return nxt
