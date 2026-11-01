"""Vfx supreme 0246.
"""
from __future__ import annotations

ID = "vfx_supreme_0246"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 246}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
