"""Vfx mega 0034.
"""
from __future__ import annotations

ID = "vfx_mega_0034"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 34}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
