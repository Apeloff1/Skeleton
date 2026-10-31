"""Loot apex 0249.
"""
from __future__ import annotations

ID = "loot_apex_0249"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 249}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
