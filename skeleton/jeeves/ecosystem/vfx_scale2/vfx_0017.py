"""Vfx scale2 0017.
"""
from __future__ import annotations

ID = "vfx_scale2_0017"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
