"""Culling 0052.
"""
from __future__ import annotations

CULL = "cull_0052"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
