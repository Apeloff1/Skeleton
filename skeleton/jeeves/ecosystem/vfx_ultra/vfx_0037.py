"""Vfx ultra 0037.
"""
from __future__ import annotations

ID = "vfx_ultra_0037"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 37}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
