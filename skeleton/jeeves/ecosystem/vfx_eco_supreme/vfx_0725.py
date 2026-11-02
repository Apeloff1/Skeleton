"""Vfx eco_supreme 0725.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0725"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 725}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
