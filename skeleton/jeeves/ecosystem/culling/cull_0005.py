"""Culling 0005.
"""
from __future__ import annotations

CULL = "cull_0005"

def frustum(visible: bool) -> dict:
    return {"ok": True, "cull": CULL, "draw": visible}
