"""Loot ultra 0128.
"""
from __future__ import annotations

ID = "loot_ultra_0128"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 128}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
