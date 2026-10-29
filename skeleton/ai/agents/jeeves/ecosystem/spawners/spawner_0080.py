"""Spawner 0080.
"""
from __future__ import annotations

SPAWNER = "spawner_0080"

def emit(count: int = 3) -> dict:
    count = max(1, min(20, int(count)))
    return {"ok": True, "spawner": SPAWNER, "count": count, "ids": [f"{SPAWNER}_{n}" for n in range(count)]}
