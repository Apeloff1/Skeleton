"""Culling 0004.
"""
from __future__ import annotations

CULL = "cull_0004"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
