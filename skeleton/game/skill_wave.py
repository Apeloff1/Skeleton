"""Wave-4 extra skills."""

from __future__ import annotations

from typing import Any


class SkillWaveError(ValueError):
    pass


SKILLS: dict[str, tuple[str, int]] = {
    f"sk_{i:02d}": (("heat", "alert", "hp", "xp", "coil")[i % 5], (i % 3) - 1)
    for i in range(20)
}


def learn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKILLS:
        raise SkillWaveError(name)
    nxt = dict(state)
    have = list(nxt.get("skills") or [])
    if name in have:
        raise SkillWaveError("have")
    if int(nxt.get("xp", 0)) < 8:
        raise SkillWaveError("xp")
    have.append(name)
    nxt["skills"] = have
    nxt["xp"] = int(nxt.get("xp", 0)) - 8
    nxt["stored_prose"] = 0
    return nxt


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKILLS:
        raise SkillWaveError(name)
    nxt = dict(state)
    if name not in list(nxt.get("skills") or []):
        raise SkillWaveError("missing")
    stat, delta = SKILLS[name]
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + delta)
    nxt["stored_prose"] = 0
    return nxt
