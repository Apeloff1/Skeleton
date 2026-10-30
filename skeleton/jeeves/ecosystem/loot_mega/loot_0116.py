"""Loot mega 0116.
"""
from __future__ import annotations

ID = "loot_mega_0116"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 116}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
