"""Culling 0027.
"""
from __future__ import annotations

CULL = "cull_0027"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
