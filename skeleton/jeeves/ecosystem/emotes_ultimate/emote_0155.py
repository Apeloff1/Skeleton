"""Emote ultimate 0155.
"""
from __future__ import annotations

ID = "emote_ultimate_0155"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 155}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
