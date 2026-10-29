"""Culling 0040.
"""
from __future__ import annotations

CULL = "cull_0040"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
