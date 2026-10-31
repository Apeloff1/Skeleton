"""Loot ultra 0141.
"""
from __future__ import annotations

ID = "loot_ultra_0141"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 141}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
