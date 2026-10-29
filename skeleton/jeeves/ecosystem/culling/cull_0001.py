"""Culling 0001.
"""
from __future__ import annotations

CULL = "cull_0001"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
