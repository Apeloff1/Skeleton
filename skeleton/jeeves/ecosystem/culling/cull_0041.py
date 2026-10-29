"""Culling 0041.
"""
from __future__ import annotations

CULL = "cull_0041"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
