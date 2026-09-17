"""Named combat beats. HP and alert."""

from __future__ import annotations

from typing import Any


class CombatPackError(ValueError):
    pass


ATK: dict[str, tuple[int, int, int]] = {
    "jab": (2, 0, 1),
    "slash": (4, 1, 2),
    "bash": (5, 2, 2),
    "poke": (1, 0, 1),
    "burnhit": (3, 2, 2),
    "chillhit": (2, 1, 1),
    "bleedhit": (3, 0, 2),
    "wardhit": (1, -2, 1),
    "scarehit": (2, 1, 1),
    "markhit": (1, 3, 1),
    "hidehit": (0, -2, 1),
    "sprinthit": (2, 2, 1),
    "coilhit": (4, 0, 2),
    "baithit": (1, -1, 1),
    "keyhit": (3, 0, 2),
    "warphit": (6, 0, 3),
}


def strike(name: str, state: dict[str, Any], foe: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if name not in ATK:
        raise CombatPackError(name)
    dmg, alert, cost = ATK[name]
    s = dict(state)
    f = dict(foe)
    if int(s.get("tokens", 8)) < cost:
        raise CombatPackError("tokens")
    f["hp"] = max(0, int(f.get("hp", 20)) - dmg)
    s["alert"] = max(0, int(s.get("alert", 0)) + alert)
    s["tokens"] = max(0, int(s.get("tokens", 8)) - cost)
    s["stored_prose"] = 0
    f["stored_prose"] = 0
    return s, f


def bout(names: list[str], seed: int) -> dict[str, Any]:
    s = {"hp": 40, "tokens": 12, "alert": 0, "seed": int(seed)}
    f = {"hp": 20, "tokens": 8, "alert": 0}
    log: list[str] = []
    for name in names:
        try:
            s, f = strike(name, s, f)
            log.append(name)
        except CombatPackError:
            break
        if f["hp"] <= 0 or s["hp"] <= 0:
            break
    winner = "player" if f["hp"] <= 0 else ("foe" if s["hp"] <= 0 else "draw")
    return {"kind": "combat_pack", "hits": log, "hp": s["hp"], "foe": f["hp"], "winner": winner, "stored_prose": 0}
