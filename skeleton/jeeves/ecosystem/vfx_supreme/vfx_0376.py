"""Vfx supreme 0376.
"""
from __future__ import annotations

ID = "vfx_supreme_0376"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 376}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
