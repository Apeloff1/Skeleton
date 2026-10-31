"""Vfx max 0169.
"""
from __future__ import annotations

ID = "vfx_max_0169"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 169}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
