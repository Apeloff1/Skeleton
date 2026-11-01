"""Vfx supreme 0272.
"""
from __future__ import annotations

ID = "vfx_supreme_0272"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 272}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
