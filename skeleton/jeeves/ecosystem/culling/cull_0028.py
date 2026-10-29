"""Culling 0028.
"""
from __future__ import annotations

CULL = "cull_0028"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
