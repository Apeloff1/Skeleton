"""Named wound sites."""

from __future__ import annotations

from typing import Any


class WoundPackError(ValueError):
    pass


SITES = (
    "head", "neck", "chest", "gut", "arm_l", "arm_r", "hand_l", "hand_r",
    "leg_l", "leg_r", "foot_l", "foot_r", "back", "side", "eye", "ear",
)


def hit(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in SITES:
        raise WoundPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("wound") or {})
    cur[name] = min(8, int(cur.get(name, 0)) + int(n))
    nxt["wound"] = cur
    nxt["hp"] = max(0, int(nxt.get("hp", 40)) - int(n))
    nxt["stored_prose"] = 0
    return nxt
