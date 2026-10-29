"""Culling 0008.
"""
from __future__ import annotations

CULL = "cull_0008"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
