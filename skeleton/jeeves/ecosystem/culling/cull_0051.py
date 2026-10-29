"""Culling 0051.
"""
from __future__ import annotations

CULL = "cull_0051"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
