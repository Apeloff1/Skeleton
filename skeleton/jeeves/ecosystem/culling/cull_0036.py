"""Culling 0036.
"""
from __future__ import annotations

CULL = "cull_0036"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
