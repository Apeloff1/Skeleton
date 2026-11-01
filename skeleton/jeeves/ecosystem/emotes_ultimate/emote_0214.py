"""Emote ultimate 0214.
"""
from __future__ import annotations

ID = "emote_ultimate_0214"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 214}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
