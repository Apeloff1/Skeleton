"""Vfx supreme 0202.
"""
from __future__ import annotations

ID = "vfx_supreme_0202"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 202}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
