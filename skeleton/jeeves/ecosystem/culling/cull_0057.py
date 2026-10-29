"""Culling 0057.
"""
from __future__ import annotations

CULL = "cull_0057"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
