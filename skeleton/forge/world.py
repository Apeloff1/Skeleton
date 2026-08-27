"""Deterministic room graph from an era pack.

A spanning tree guarantees extract is reachable from spawn; extra chords
are era-tempo: faster dialects get more loops. Seeded from the tensor
fingerprint when present, else the era name.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Tuple

KINDS = ("spawn", "combat", "loot", "heat", "extract")


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def generate_rooms(pack: Dict[str, Any], *, seed: str | None = None) -> Dict[str, Any]:
    session = pack.get("session") or {}
    lo = int(session.get("room_count_min") or 6)
    hi = int(session.get("room_count_max") or 12)
    lo, hi = max(3, lo), max(lo, hi)
    rng = _rng(seed or str(pack.get("era") or "extraction_now"))
    n = rng.randint(lo, min(hi, lo + 8))
    rooms: List[Dict[str, Any]] = []
    for i in range(n):
        if i == 0:
            kind = "spawn"
        elif i == n - 1:
            kind = "extract"
        else:
            kind = rng.choice(("combat", "combat", "loot", "heat"))
        rooms.append({"id": f"r{i:02d}", "kind": kind, "index": i})
    edges: List[Tuple[str, str]] = []
    # spanning tree along the index so extract is always reachable
    for i in range(n - 1):
        edges.append((rooms[i]["id"], rooms[i + 1]["id"]))
    extra = max(0, n // 4)
    for _ in range(extra):
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b:
            continue
        u, v = rooms[min(a, b)]["id"], rooms[max(a, b)]["id"]
        if (u, v) not in edges:
            edges.append((u, v))
    return {
        "era": pack.get("era"),
        "count": n,
        "rooms": rooms,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "reachable": True,
    }


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
