"""Vfx supreme 0238.
"""
from __future__ import annotations

ID = "vfx_supreme_0238"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 238}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
