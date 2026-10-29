"""Culling 0053.
"""
from __future__ import annotations

CULL = "cull_0053"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
