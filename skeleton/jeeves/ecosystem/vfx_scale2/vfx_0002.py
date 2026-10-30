"""Vfx scale2 0002.
"""
from __future__ import annotations

ID = "vfx_scale2_0002"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 2}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
