"""Vfx ultra_max 0273.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0273"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
