"""Vfx ultimate 0371.
"""
from __future__ import annotations

ID = "vfx_ultimate_0371"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 371}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
