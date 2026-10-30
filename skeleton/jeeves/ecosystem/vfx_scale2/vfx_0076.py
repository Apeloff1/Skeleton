"""Vfx scale2 0076.
"""
from __future__ import annotations

ID = "vfx_scale2_0076"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 76}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
