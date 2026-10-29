"""Culling 0045.
"""
from __future__ import annotations

CULL = "cull_0045"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
