"""Culling 0035.
"""
from __future__ import annotations

CULL = "cull_0035"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
