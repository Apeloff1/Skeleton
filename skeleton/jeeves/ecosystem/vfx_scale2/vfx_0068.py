"""Vfx scale2 0068.
"""
from __future__ import annotations

ID = "vfx_scale2_0068"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 68}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
