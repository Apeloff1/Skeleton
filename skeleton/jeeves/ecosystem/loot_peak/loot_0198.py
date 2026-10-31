"""Loot peak 0198.
"""
from __future__ import annotations

ID = "loot_peak_0198"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 198}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
