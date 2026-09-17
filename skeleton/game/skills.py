"""Skill tree evaluator. Named nodes."""

from __future__ import annotations

from typing import Any


class SkillError(ValueError):
    pass


NODES = {
    "heat_ward": ("heat", -2, "def", 1),
    "forge_hand": ("parts", 1, "atk", 1),
    "quiet_step": ("alert", -1, "spd", 1),
    "scrap_eye": ("scrap", 1, "xp", 2),
    "dream_cut": ("dreams", 1, "heat", -2),
    "extract_will": ("extract_ready", 1, "hp", 4),
}


def learn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NODES:
        raise SkillError(name)
    if int(state.get("xp", 0)) < 5:
        raise SkillError("xp")
    a, da, b, db = NODES[name]
    nxt = dict(state)
    nxt["xp"] = int(nxt.get("xp", 0)) - 5
    nxt[a] = int(nxt.get(a, 0)) + da
    nxt[b] = int(nxt.get(b, 0)) + db
    learned = list(nxt.get("skills") or [])
    if name not in learned:
        learned.append(name)
    nxt["skills"] = learned
    nxt["stored_prose"] = 0
    return nxt


def tree() -> list[dict[str, Any]]:
    return [
        {"skill": name, "cost_xp": 5, "a": a, "da": da, "b": b, "db": db, "stored_prose": 0}
        for name, (a, da, b, db) in NODES.items()
    ]
