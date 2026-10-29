"""Culling 0009.
"""
from __future__ import annotations

CULL = "cull_0009"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
