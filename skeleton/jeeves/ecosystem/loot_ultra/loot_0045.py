"""Loot ultra 0045.
"""
from __future__ import annotations

ID = "loot_ultra_0045"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 45}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
