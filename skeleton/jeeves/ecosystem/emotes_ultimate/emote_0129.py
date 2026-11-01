"""Emote ultimate 0129.
"""
from __future__ import annotations

ID = "emote_ultimate_0129"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 129}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
