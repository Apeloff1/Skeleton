"""Vfx eco_supreme 0126.
"""
from __future__ import annotations

ID = "vfx_eco_supreme_0126"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
