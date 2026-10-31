"""Loot peak 0196.
"""
from __future__ import annotations

ID = "loot_peak_0196"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 196}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
