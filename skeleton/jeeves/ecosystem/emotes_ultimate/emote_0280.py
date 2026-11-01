"""Emote ultimate 0280.
"""
from __future__ import annotations

ID = "emote_ultimate_0280"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 280}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
