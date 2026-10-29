"""Culling 0006.
"""
from __future__ import annotations

CULL = "cull_0006"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
