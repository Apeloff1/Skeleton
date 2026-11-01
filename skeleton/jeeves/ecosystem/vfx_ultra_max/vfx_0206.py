"""Vfx ultra_max 0206.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0206"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 206}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
