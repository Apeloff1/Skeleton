"""Vfx max 0138.
"""
from __future__ import annotations

ID = "vfx_max_0138"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 138}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
