"""Vfx ultra_max 0188.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0188"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 188}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
