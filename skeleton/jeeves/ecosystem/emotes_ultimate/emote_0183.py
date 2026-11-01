"""Emote ultimate 0183.
"""
from __future__ import annotations

ID = "emote_ultimate_0183"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 183}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
