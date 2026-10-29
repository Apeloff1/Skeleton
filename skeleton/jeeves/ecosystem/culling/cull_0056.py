"""Culling 0056.
"""
from __future__ import annotations

CULL = "cull_0056"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
