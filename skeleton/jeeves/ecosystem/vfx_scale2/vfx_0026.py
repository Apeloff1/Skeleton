"""Vfx scale2 0026.
"""
from __future__ import annotations

ID = "vfx_scale2_0026"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 26}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
