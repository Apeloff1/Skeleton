"""Culling 0011.
"""
from __future__ import annotations

CULL = "cull_0011"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
