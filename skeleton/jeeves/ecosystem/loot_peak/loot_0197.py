"""Loot peak 0197.
"""
from __future__ import annotations

ID = "loot_peak_0197"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 197}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
