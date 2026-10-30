"""Vfx mega 0087.
"""
from __future__ import annotations

ID = "vfx_mega_0087"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 87}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
