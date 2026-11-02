"""Vfx eco_supreme 0721.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0721"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 721}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
