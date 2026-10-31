"""Vfx ultra 0134.
"""
from __future__ import annotations

ID = "vfx_ultra_0134"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
