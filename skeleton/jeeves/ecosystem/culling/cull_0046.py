"""Culling 0046.
"""
from __future__ import annotations

CULL = "cull_0046"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
