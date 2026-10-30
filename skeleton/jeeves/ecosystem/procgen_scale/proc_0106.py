"""Procgen scale 0106.
"""
from __future__ import annotations

PROC = "proc_scale_0106"

def rooms(count: int = 8, optical: float = 0.9) -> list[dict]:
    count = max(2, min(48, int(count)))
    out = []
    for n in range(count):
        kind = "boss" if n == count - 1 else ("shop" if n % 6 == 0 else "combat")
        out.append({"id": n, "kind": kind, "seed": 2106 + n, "weight": round(optical * (1 + n * 0.02), 3)})
    return out

def noise(x: float, y: float) -> float:
    return round(((x * 12.9898 + y * 78.233 + 106) % 1.0), 4)
