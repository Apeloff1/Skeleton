"""Vfx ultimate 0393.
"""
from __future__ import annotations

ID = "vfx_ultimate_0393"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 393}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
