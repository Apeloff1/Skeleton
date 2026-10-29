"""Culling 0054.
"""
from __future__ import annotations

CULL = "cull_0054"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
