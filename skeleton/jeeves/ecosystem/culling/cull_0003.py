"""Culling 0003.
"""
from __future__ import annotations

CULL = "cull_0003"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
