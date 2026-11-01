"""Vfx ultra_max 0083.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0083"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 83}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
