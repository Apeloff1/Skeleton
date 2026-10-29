"""Culling 0059.
"""
from __future__ import annotations

CULL = "cull_0059"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
