"""Vfx ultra_max 0291.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0291"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 291}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
