"""Procedural seed 015 — deterministic room and loot placement.
"""
from __future__ import annotations

SEED = 1015

def rooms(count: int = 6, optical: float = 0.9) -> list[dict]:
    count = max(2, min(64, int(count)))
    out = []
    for n in range(count):
        kind = "boss" if n == count - 1 else ("shop" if n % 5 == 0 else "combat")
        out.append({"id": n, "kind": kind, "seed": SEED + n, "weight": round(optical * (1 + n * 0.05), 3)})
    return out

def edges(count: int) -> list[list[int]]:
    count = max(2, int(count))
    return [[i, i + 1] for i in range(count - 1)] + ([[0, count - 1]] if count > 3 else [])

def loot(optical: float = 0.9) -> str:
    if optical > 0.95:
        return "epic"
    if optical > 0.9:
        return "rare"
    return "common"
