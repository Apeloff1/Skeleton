"""Loot mega 0038.
"""
from __future__ import annotations

ID = "loot_mega_0038"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 38}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
