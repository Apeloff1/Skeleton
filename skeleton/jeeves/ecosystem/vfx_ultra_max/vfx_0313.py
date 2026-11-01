"""Vfx ultra_max 0313.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0313"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 313}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
