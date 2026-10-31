"""Vfx ultra 0100.
"""
from __future__ import annotations

ID = "vfx_ultra_0100"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 100}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
