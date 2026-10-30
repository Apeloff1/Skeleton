"""Vfx mega 0099.
"""
from __future__ import annotations

ID = "vfx_mega_0099"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
