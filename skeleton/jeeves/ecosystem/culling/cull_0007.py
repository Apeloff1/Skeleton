"""Culling 0007.
"""
from __future__ import annotations

CULL = "cull_0007"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
