"""Vfx eco_supreme 0563.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0563"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 563}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
