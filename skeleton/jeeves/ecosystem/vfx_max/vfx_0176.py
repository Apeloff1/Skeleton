"""Vfx max 0176.
"""
from __future__ import annotations

ID = "vfx_max_0176"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 176}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
