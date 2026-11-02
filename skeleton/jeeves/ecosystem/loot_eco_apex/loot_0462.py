"""Loot eco_apex 0462.
"""
from __future__ import annotations

ID = "loot_eco_apex_0462"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 462}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
