"""Loot ultra 0089.
"""
from __future__ import annotations

ID = "loot_ultra_0089"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 89}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
