"""Emote ultimate 0298.
"""
from __future__ import annotations

ID = "emote_ultimate_0298"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 298}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
