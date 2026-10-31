"""Vfx ultra 0140.
"""
from __future__ import annotations

ID = "vfx_ultra_0140"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 140}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
