"""Culling 0044.
"""
from __future__ import annotations

CULL = "cull_0044"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
