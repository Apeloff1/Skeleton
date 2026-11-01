"""Vfx ultimate 0325.
"""
from __future__ import annotations

ID = "vfx_ultimate_0325"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 325}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
