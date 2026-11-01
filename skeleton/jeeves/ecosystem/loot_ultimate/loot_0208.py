"""Loot ultimate 0208.
"""
from __future__ import annotations

ID = "loot_ultimate_0208"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 208}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
