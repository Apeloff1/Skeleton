"""Culling 0013.
"""
from __future__ import annotations

CULL = "cull_0013"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
