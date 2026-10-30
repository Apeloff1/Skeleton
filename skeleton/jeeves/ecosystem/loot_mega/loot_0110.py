"""Loot mega 0110.
"""
from __future__ import annotations

ID = "loot_mega_0110"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 110}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
