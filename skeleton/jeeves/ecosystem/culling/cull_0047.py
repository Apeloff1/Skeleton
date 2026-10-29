"""Culling 0047.
"""
from __future__ import annotations

CULL = "cull_0047"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
