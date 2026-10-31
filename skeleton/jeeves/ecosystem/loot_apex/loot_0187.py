"""Loot apex 0187.
"""
from __future__ import annotations

ID = "loot_apex_0187"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 187}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
