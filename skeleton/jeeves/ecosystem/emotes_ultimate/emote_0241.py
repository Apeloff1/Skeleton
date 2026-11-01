"""Emote ultimate 0241.
"""
from __future__ import annotations

ID = "emote_ultimate_0241"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 241}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
