"""Vfx ultimate 0237.
"""
from __future__ import annotations

ID = "vfx_ultimate_0237"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 237}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
