"""Vfx supreme 0399.
"""
from __future__ import annotations

ID = "vfx_supreme_0399"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 399}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
