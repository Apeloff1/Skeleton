"""Culling 0021.
"""
from __future__ import annotations

CULL = "cull_0021"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
