"""Culling 0015.
"""
from __future__ import annotations

CULL = "cull_0015"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
