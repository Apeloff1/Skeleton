"""Culling 0012.
"""
from __future__ import annotations

CULL = "cull_0012"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
