"""Vfx ultra 0106.
"""
from __future__ import annotations

ID = "vfx_ultra_0106"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 106}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
