"""Culling 0042.
"""
from __future__ import annotations

CULL = "cull_0042"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
