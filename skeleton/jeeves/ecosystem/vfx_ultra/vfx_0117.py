"""Vfx ultra 0117.
"""
from __future__ import annotations

ID = "vfx_ultra_0117"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 117}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
