"""Vfx ultimate 0433.
"""
from __future__ import annotations

ID = "vfx_ultimate_0433"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 433}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
