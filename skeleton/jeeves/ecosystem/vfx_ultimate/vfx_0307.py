"""Vfx ultimate 0307.
"""
from __future__ import annotations

ID = "vfx_ultimate_0307"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 307}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
