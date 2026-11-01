"""Vfx ultra_max 0240.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0240"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 240}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
