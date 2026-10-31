"""Loot ultra 0138.
"""
from __future__ import annotations

ID = "loot_ultra_0138"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 138}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
