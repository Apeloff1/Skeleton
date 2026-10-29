"""Culling 0020.
"""
from __future__ import annotations

CULL = "cull_0020"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
