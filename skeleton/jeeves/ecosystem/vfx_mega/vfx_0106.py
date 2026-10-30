"""Vfx mega 0106.
"""
from __future__ import annotations

ID = "vfx_mega_0106"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 106}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
