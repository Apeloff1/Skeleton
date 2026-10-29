"""Culling 0043.
"""
from __future__ import annotations

CULL = "cull_0043"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
