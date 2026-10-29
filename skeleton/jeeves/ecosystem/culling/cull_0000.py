"""Culling 0000.
"""
from __future__ import annotations

CULL = "cull_0000"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
