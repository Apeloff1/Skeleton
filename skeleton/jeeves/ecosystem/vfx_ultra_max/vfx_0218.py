"""Vfx ultra_max 0218.
"""
from __future__ import annotations

ID = "vfx_ultra_max_0218"

def describe() -> dict:
    return {"id": ID, "kind": "vfx", "index": 218}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
