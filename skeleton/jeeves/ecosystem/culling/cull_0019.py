"""Culling 0019.
"""
from __future__ import annotations

CULL = "cull_0019"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
