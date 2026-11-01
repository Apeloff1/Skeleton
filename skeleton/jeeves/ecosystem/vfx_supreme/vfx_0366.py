"""Vfx supreme 0366.
"""
from __future__ import annotations

ID = "vfx_supreme_0366"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 366}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
