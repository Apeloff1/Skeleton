"""Culling 0034.
"""
from __future__ import annotations

CULL = "cull_0034"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
