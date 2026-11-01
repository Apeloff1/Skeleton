"""Emote ultimate 0137.
"""
from __future__ import annotations

ID = "emote_ultimate_0137"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 137}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
