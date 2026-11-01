"""Emote ultimate 0174.
"""
from __future__ import annotations

ID = "emote_ultimate_0174"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
