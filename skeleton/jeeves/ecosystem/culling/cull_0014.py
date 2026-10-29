"""Culling 0014.
"""
from __future__ import annotations

CULL = "cull_0014"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
