"""Culling 0026.
"""
from __future__ import annotations

CULL = "cull_0026"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
