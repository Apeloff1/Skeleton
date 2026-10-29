"""Culling 0010.
"""
from __future__ import annotations

CULL = "cull_0010"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
