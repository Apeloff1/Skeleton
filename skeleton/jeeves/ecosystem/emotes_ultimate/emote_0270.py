"""Emote ultimate 0270.
"""
from __future__ import annotations

ID = "emote_ultimate_0270"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 270}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
