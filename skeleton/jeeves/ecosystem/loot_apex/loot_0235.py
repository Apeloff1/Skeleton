"""Loot apex 0235.
"""
from __future__ import annotations

ID = "loot_apex_0235"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 235}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
