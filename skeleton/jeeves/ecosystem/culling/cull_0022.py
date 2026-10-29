"""Culling 0022.
"""
from __future__ import annotations

CULL = "cull_0022"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
