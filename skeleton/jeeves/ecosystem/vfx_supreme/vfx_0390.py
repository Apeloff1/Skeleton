"""Vfx supreme 0390.
"""
from __future__ import annotations

ID = "vfx_supreme_0390"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 390}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
