"""Loot eco_supreme 0760.
"""
from __future__ import annotations

ID = "loot_eco_supreme_0760"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 760}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
