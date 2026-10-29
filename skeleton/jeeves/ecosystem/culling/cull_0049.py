"""Culling 0049.
"""
from __future__ import annotations

CULL = "cull_0049"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
