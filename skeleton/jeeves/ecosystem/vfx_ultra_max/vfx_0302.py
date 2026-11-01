"""Vfx ultra_max 0302.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0302"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 302}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
