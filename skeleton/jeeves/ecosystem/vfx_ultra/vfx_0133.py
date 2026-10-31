"""Vfx ultra 0133.
"""
from __future__ import annotations

ID = "vfx_ultra_0133"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
