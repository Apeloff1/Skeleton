"""Emote ultimate 0230.
"""
from __future__ import annotations

ID = "emote_ultimate_0230"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 230}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
