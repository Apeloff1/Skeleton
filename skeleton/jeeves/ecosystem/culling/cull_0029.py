"""Culling 0029.
"""
from __future__ import annotations

CULL = "cull_0029"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
