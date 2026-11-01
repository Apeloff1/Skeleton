"""Vfx supreme 0227.
"""
from __future__ import annotations

ID = "vfx_supreme_0227"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 227}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
