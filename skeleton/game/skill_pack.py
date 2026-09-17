"""Named skills. Learn once."""

from __future__ import annotations

from typing import Any


class SkillPackError(ValueError):
    pass


SKILLS: dict[str, tuple[str, int]] = {
    "heat_ward": ("heat", -1), "deep_sleep": ("sleep", 2), "lockpick": ("key", 1),
    "barter_plus": ("scrap", 1), "craft_plus": ("parts", 1), "quiet_step": ("alert", -1),
    "loud_call": ("alert", 2), "fog_eye": ("los_pen", -1), "shaft_leg": ("floor", 0),
    "extract_sense": ("heat", 0), "coil_tune": ("coil", 1), "bait_craft": ("bait", 1),
    "mend_hand": ("hp", 2), "bleed_know": ("hp", -1), "quest_mark": ("xp", 1),
    "talk_soft": ("xp", 1), "save_habit": ("saved", 0), "doctor_eye": ("mass", 0),
    "clip_hand": ("mass", 0), "warp_read": ("warp_count", 0), "mesh_pass": ("tokens", 1),
    "crowd_read": ("occupancy", 0), "hunt_ear": ("alert", 1), "seal_hand": ("digest", 0),
}


def learn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKILLS:
        raise SkillPackError(name)
    nxt = dict(state)
    have = list(nxt.get("skills") or [])
    if name in have:
        raise SkillPackError("have")
    if int(nxt.get("xp", 0)) < 8:
        raise SkillPackError("xp")
    have.append(name)
    nxt["skills"] = have
    nxt["xp"] = int(nxt.get("xp", 0)) - 8
    nxt["stored_prose"] = 0
    return nxt


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKILLS:
        raise SkillPackError(name)
    nxt = dict(state)
    if name not in list(nxt.get("skills") or []):
        raise SkillPackError("missing")
    stat, delta = SKILLS[name]
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + delta)
    nxt["stored_prose"] = 0
    return nxt
