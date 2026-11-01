"""Emote ultimate 0245.
"""
from __future__ import annotations

ID = "emote_ultimate_0245"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 245}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
