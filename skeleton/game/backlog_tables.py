"""Backlog tables. Remaining named packs compressed to max API density."""

from __future__ import annotations

from typing import Any


class BacklogError(ValueError):
    pass


FOG = tuple(f"fog_{i:02d}" for i in range(16))
ROLES = (
    "scout", "chaser", "blocker", "sentry", "baiter", "warden",
    "runner", "sleeper", "forger", "clerk", "doctor", "clipper",
    "herald", "rat", "monk", "ref",
)
PRESSURE = tuple(f"p{i:02d}" for i in range(20))
SAVES = tuple(f"slot{i}" for i in range(12))
TILES = (
    "floor", "vent", "ash", "fog", "lock", "heat", "extract", "spawn",
    "stair", "shaft", "bridge", "dead", "cycle", "water", "coil", "scrap",
    "bait", "dream", "seal", "crowd", "quiet", "loud", "ward", "warp",
)
DOORS = (
    "wood", "iron", "vent", "shaft", "extract", "lockbox", "fogdoor", "heatgate",
    "cell", "stair", "bridge", "cycle", "dead", "dream", "seal", "warp",
)
SKILLS = (
    "heat_ward", "deep_sleep", "lockpick", "barter_plus", "craft_plus", "quiet_step",
    "loud_call", "fog_eye", "shaft_leg", "extract_sense", "coil_tune", "bait_craft",
    "mend_hand", "bleed_know", "quest_mark", "talk_soft", "save_habit", "doctor_eye",
    "clip_hand", "warp_read", "mesh_pass", "crowd_read", "hunt_ear", "seal_hand",
)
CRAFT = {
    "coil": (("scrap", 2), ("parts", 1)),
    "bait": (("scrap", 1),),
    "key": (("parts", 2),),
    "ward": (("coil", 1), ("scrap", 1)),
    "patch": (("scrap", 1), ("parts", 1)),
}


def fog_apply(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in FOG:
        raise BacklogError(name)
    nxt = dict(state)
    nxt["fog_bank"] = name
    nxt["los_pen"] = max(0, min(8, FOG.index(name) % 5 + (t % 3) - 1))
    nxt["stored_prose"] = 0
    return nxt


def role_step(agent: dict[str, Any], player: str, t: int) -> dict[str, Any]:
    role = str(agent.get("role") or "")
    if role not in ROLES:
        raise BacklogError(role)
    nxt = dict(agent)
    i = ROLES.index(role)
    if i % 2 == 0:
        nxt["room"] = player
    nxt["alert"] = int(nxt.get("room") == player)
    nxt["stored_prose"] = 0
    return nxt


def pressure_relax(name: str, value: int, neighbors: list[int]) -> int:
    if name not in PRESSURE:
        raise BacklogError(name)
    i = PRESSURE.index(name)
    if not neighbors:
        return max(0, min(16, int(value) + ((i % 5) - 2)))
    avg = sum(int(n) for n in neighbors) / len(neighbors)
    return max(0, min(16, int(round((int(value) * 2 + avg + (i % 3)) / 3))))


def save_write(bank: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in SAVES:
        raise BacklogError(name)
    if not digest:
        raise BacklogError("digest")
    nxt = dict(bank)
    nxt[name] = {"digest": digest, "stored_prose": 0}
    return nxt


def tile_enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TILES:
        raise BacklogError(name)
    nxt = dict(state)
    nxt["tile"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((TILES.index(name) % 5) - 2)))
    nxt["stored_prose"] = 0
    return nxt


def door_make(name: str) -> dict[str, Any]:
    if name not in DOORS:
        raise BacklogError(name)
    locked = name in {"iron", "extract", "lockbox", "cell", "dead", "seal", "warp"}
    return {"door": name, "open": not locked, "locked": locked, "stored_prose": 0}


def skill_learn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKILLS:
        raise BacklogError(name)
    nxt = dict(state)
    have = list(nxt.get("skills") or [])
    if name in have:
        raise BacklogError("have")
    if int(nxt.get("xp", 0)) < 8:
        raise BacklogError("xp")
    have.append(name)
    nxt["skills"] = have
    nxt["xp"] = int(nxt.get("xp", 0)) - 8
    nxt["stored_prose"] = 0
    return nxt


def census() -> dict[str, int]:
    return {
        "fog": len(FOG),
        "roles": len(ROLES),
        "pressure": len(PRESSURE),
        "saves": len(SAVES),
        "tiles": len(TILES),
        "doors": len(DOORS),
        "skills": len(SKILLS),
        "craft": len(CRAFT),
        "stored_prose": 0,
    }
