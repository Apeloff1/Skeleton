"""Emote ultimate 0285.
"""
from __future__ import annotations

ID = "emote_ultimate_0285"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 285}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
