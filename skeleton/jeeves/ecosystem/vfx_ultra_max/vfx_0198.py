"""Vfx ultra_max 0198.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0198"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 198}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
