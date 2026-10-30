"""Loot mega 0065.
"""
from __future__ import annotations

ID = "loot_mega_0065"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 65}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
