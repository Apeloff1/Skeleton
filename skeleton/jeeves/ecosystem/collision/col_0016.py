"""Collision 0016.
"""
from __future__ import annotations

COL = "col_0016"

def aabb(min_a: list, max_a: list, min_b: list, max_b: list) -> dict:
    hit = all(min_a[i] <= max_b[i] and max_a[i] >= min_b[i] for i in range(min(2, len(min_a))))
    return {"ok": True, "col": COL, "hit": hit}
