"""Culling 0025.
"""
from __future__ import annotations

CULL = "cull_0025"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
