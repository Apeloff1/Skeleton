"""Minigame 0025.
"""
from __future__ import annotations

MINI = "mini_0025"

def score(hits: int, misses: int) -> dict:
    total = max(1, hits + misses)
    return {"ok": True, "mini": MINI, "score": hits, "accuracy": round(hits / total, 3)}
