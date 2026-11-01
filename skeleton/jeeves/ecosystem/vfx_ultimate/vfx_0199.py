"""Vfx ultimate 0199.
"""
from __future__ import annotations

ID = "vfx_ultimate_0199"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 199}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
