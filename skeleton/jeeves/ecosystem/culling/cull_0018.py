"""Culling 0018.
"""
from __future__ import annotations

CULL = "cull_0018"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
