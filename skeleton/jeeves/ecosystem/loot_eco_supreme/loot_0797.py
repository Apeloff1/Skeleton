"""Loot eco_supreme 0797.
"""
from __future__ import annotations

ID = "loot_eco_supreme_0797"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 797}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
