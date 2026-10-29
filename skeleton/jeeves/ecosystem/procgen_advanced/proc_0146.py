"""Procgen 0146.
"""
from __future__ import annotations

PROC = "proc_0146"

def rooms(count: int = 8, optical: float = 0.9) -> list[dict]:
    count = max(2, min(32, int(count)))
    out = []
    for n in range(count):
        kind = "boss" if n == count - 1 else ("shop" if n % 5 == 0 else "combat")
        out.append({"id": n, "kind": kind, "seed": 1146 + n, "weight": round(optical * (1 + n * 0.03), 3)})
    return out

def noise(x: float, y: float) -> float:
    return round(((x * 12.9898 + y * 78.233 + 146) % 1.0), 4)
