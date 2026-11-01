"""Vfx ultimate 0396.
"""
from __future__ import annotations

ID = "vfx_ultimate_0396"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 396}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
