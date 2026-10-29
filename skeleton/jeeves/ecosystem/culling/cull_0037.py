"""Culling 0037.
"""
from __future__ import annotations

CULL = "cull_0037"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
