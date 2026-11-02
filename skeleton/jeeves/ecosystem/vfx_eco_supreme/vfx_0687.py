"""Vfx eco_supreme 0687.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0687"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 687}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
