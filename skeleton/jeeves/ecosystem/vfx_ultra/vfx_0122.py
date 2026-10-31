"""Vfx ultra 0122.
"""
from __future__ import annotations

ID = "vfx_ultra_0122"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 122}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
