"""Culling 0002.
"""
from __future__ import annotations

CULL = "cull_0002"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
