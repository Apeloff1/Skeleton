"""Vfx eco_supreme 0717.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0717"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 717}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
