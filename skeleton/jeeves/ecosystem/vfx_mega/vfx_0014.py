"""Vfx mega 0014.
"""
from __future__ import annotations

ID = "vfx_mega_0014"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 14}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
