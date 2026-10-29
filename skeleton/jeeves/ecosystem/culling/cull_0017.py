"""Culling 0017.
"""
from __future__ import annotations

CULL = "cull_0017"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
