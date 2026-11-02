"""Vfx eco_supreme 0737.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0737"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 737}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
