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


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def generate_rooms(
    pack: Dict[str, Any],
    *,
    seed: str | None = None,
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session = pack.get("session") or {}
    lo = int(session.get("room_count_min") or 6)
    hi = int(session.get("room_count_max") or 12)
    lo, hi = max(3, lo), max(lo, hi)
    plan = plan or {}
    seed = seed or str(plan.get("seed") or pack.get("era") or "extraction_now")
    rng = _rng(seed)
    # keep graphs bounded so the instanced tscn stays a project, not a novel
    n = rng.randint(lo, min(hi, lo + 8, 24))
    bias = str(plan.get("room_bias") or "balanced")
    bag = _BIAS.get(bias, _BIAS["balanced"])
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
    if str(plan.get("extract_late")) in {"True", "true", "1"}:
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
        "spawn_weapon": bool(plan.get("spawn_weapon")),
        "extract_late": bool(plan.get("extract_late")),
        "occupancy": occupant_counts({"rooms": rooms}),
    }


def _populate(
    rooms: List[Dict[str, Any]],
    pack: Dict[str, Any],
    plan: Dict[str, Any],
    rng: random.Random,
) -> None:
    mix = plan.get("enemy_mix") or {}
    trash_n = int(mix.get("trash") or 2)
    elite_n = int(mix.get("elite") or 0)
    boss_n = int(mix.get("boss") or 0)
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
            k = occ.get("kind") or "loot"
            counts[k] = counts.get(k, 0) + 1
    return counts
