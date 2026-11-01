"""Vfx supreme 0301.
"""
from __future__ import annotations

ID = "vfx_supreme_0301"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 301}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
