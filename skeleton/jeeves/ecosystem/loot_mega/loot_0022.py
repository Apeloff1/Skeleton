"""Loot mega 0022.
"""
from __future__ import annotations

ID = "loot_mega_0022"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 22}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
