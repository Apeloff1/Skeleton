"""Loot eco_apex 0396.
"""
from __future__ import annotations

ID = "loot_eco_apex_0396"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 396}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
