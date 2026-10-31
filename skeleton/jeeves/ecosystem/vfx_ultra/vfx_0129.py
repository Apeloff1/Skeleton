"""Vfx ultra 0129.
"""
from __future__ import annotations

ID = "vfx_ultra_0129"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 129}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
