"""Vfx ultra 0127.
"""
from __future__ import annotations

ID = "vfx_ultra_0127"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 127}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
