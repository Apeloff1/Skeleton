"""Deterministic room graph from an era pack + optional Jeeves BuildPlan.

A spanning tree guarantees extract is reachable from spawn; extra chords
are era-tempo: faster dialects get more loops. Occupants (player, enemies,
extract, heat) are assigned here so the Godot emitter instances the graph
instead of a three-node demo hallway. Seeded from the plan seed, else
the tensor fingerprint, else the era name.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("spawn", "combat", "loot", "heat", "extract")
_BIAS: Dict[str, Tuple[str, ...]] = {
    "combat": ("combat", "combat", "combat", "loot", "heat"),
    "loot": ("loot", "loot", "combat", "combat", "heat"),
    "heat": ("heat", "heat", "combat", "loot", "combat"),
    "balanced": ("combat", "combat", "loot", "heat"),
}
ROOM_W, ROOM_H = 640, 360



def _count(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _flag(value, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _optional_flag(value, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    return _flag(value, label)


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def generate_rooms(
    pack: Dict[str, Any],
    *,
    seed: str | None = None,
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(pack, dict):
        raise ValueError("pack is required")
    session = pack.get("session") if isinstance(pack.get("session"), dict) else {}
    lo = _count(session.get("room_count_min"), "room_count_min")
    hi = _count(session.get("room_count_max"), "room_count_max")
    if lo < 3 or hi < lo:
        raise ValueError("room counts must be at least 3 and max must be >= min")
    plan = plan or {}
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    if seed is None:
        seed = plan.get("seed") or pack.get("era")
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("seed is required")
    rng = _rng(seed)
    n = rng.randint(lo, min(hi, lo + 8, 24))
    bias = plan.get("room_bias")
    if bias is None:
        bias = pack.get("room_bias")
    if bias is None:
        bias = "balanced"
    if not isinstance(bias, str) or bias not in _BIAS:
        raise ValueError(f"unknown room_bias {bias!r}")
    bag = _BIAS[bias]
    rooms: List[Dict[str, Any]] = []
    for i in range(n):
        if i == 0:
            kind = "spawn"
        elif i == n - 1:
            kind = "extract"
        else:
            kind = rng.choice(bag)
        col, row = i % 4, i // 4
        rooms.append({
            "id": f"r{i:02d}",
            "kind": kind,
            "index": i,
            "x": col * ROOM_W + ROOM_W // 2,
            "y": row * ROOM_H + ROOM_H // 2,
            "occupants": [],
        })
    edges: List[Tuple[str, str]] = []
    for i in range(n - 1):
        edges.append((rooms[i]["id"], rooms[i + 1]["id"]))
    extra = max(0, n // 4)
    if plan.get("extract_late") is True:
        extra = max(extra, n // 3)
    for _ in range(extra):
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b:
            continue
        u, v = rooms[min(a, b)]["id"], rooms[max(a, b)]["id"]
        if (u, v) not in edges:
            edges.append((u, v))
    _populate(rooms, pack, plan, rng)
    doors = _doors(rooms, edges)
    return {
        "era": pack.get("era"),
        "seed": seed,
        "bias": bias,
        "count": n,
        "rooms": rooms,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "doors": doors,
        "reachable": True,
        "spawn_weapon": _optional_flag(plan.get("spawn_weapon"), "spawn_weapon"),
        "extract_late": _optional_flag(plan.get("extract_late"), "extract_late"),
        "occupancy": occupant_counts({"rooms": rooms}),
    }


def _populate(
    rooms: List[Dict[str, Any]],
    pack: Dict[str, Any],
    plan: Dict[str, Any],
    rng: random.Random,
) -> None:
    mix = plan.get("enemy_mix") if isinstance(plan.get("enemy_mix"), dict) else {}
    trash_n = _count(mix["trash"], "trash") if "trash" in mix else 0
    elite_n = _count(mix["elite"], "elite") if "elite" in mix else 0
    boss_n = _count(mix["boss"], "boss") if "boss" in mix else 0
    combat = [r for r in rooms if r["kind"] == "combat"]
    for r in rooms:
        if r["kind"] == "spawn":
            r["occupants"].append({"kind": "player", "tier": None})
        elif r["kind"] == "extract":
            r["occupants"].append({"kind": "extract", "tier": None})
        elif r["kind"] == "heat":
            r["occupants"].append({"kind": "heat", "tier": None})
        elif r["kind"] == "loot":
            r["occupants"].append({"kind": "loot", "tier": None})
    if not combat:
        return
    # spread the planned mix; do not invent a trash per combat room
    for i in range(trash_n):
        room = combat[i % len(combat)]
        room["occupants"].append({"kind": "enemy", "tier": "trash"})
    for i in range(elite_n):
        room = combat[-(i + 1)] if combat else rooms[-2]
        room["occupants"].append({"kind": "enemy", "tier": "elite"})
    if boss_n and combat:
        combat[-1]["occupants"].append({"kind": "enemy", "tier": "boss"})
    _ = rng  # seed consumed by caller; keep signature stable for later jitter


def _sign(v: float) -> int:
    return 0 if v == 0 else (1 if v > 0 else -1)


def _doors(rooms: List[Dict[str, Any]], edges: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    by = {r["id"]: r for r in rooms}
    out: List[Dict[str, Any]] = []
    for a, b in edges:
        ra, rb = by[a], by[b]
        sx = _sign(rb["x"] - ra["x"])
        sy = _sign(rb["y"] - ra["y"])
        out.append({
            "from": a, "to": b,
            "x": sx * (ROOM_W // 2 - 24), "y": sy * (ROOM_H // 2 - 24),
            "dest_x": -sx * 80, "dest_y": -sy * 80,
        })
        out.append({
            "from": b, "to": a,
            "x": -sx * (ROOM_W // 2 - 24), "y": -sy * (ROOM_H // 2 - 24),
            "dest_x": sx * 80, "dest_y": sy * 80,
        })
    return out


def assert_connected(graph: Dict[str, Any]) -> None:
    rooms = [r["id"] for r in graph["rooms"]]
    adj = {r: [] for r in rooms}
    for e in graph["edges"]:
        adj[e["from"]].append(e["to"])
        adj[e["to"]].append(e["from"])
    seen = {rooms[0]}
    stack = [rooms[0]]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    if seen != set(rooms):
        raise ValueError("room graph is not connected")


def assert_occupancy(graph: Dict[str, Any]) -> None:
    counts = occupant_counts(graph)
    if counts.get("player", 0) != 1:
        raise ValueError("spawn occupancy: expected exactly one player")
    if counts.get("extract", 0) != 1:
        raise ValueError("extract occupancy: expected exactly one extract")
    doors = graph.get("doors") or []
    if len(doors) != 2 * len(graph.get("edges") or []):
        raise ValueError("doors are not bidirectional")


def occupant_counts(graph: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {"player": 0, "enemy": 0, "extract": 0, "heat": 0, "loot": 0}
    for room in graph["rooms"]:
        for occ in room.get("occupants") or []:
            kind = occ.get("kind")
            if kind not in counts:
                continue
            counts[kind] += 1
    return counts
