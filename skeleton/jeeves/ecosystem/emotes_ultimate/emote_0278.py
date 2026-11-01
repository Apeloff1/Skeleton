"""Emote ultimate 0278.
"""
from __future__ import annotations

ID = "emote_ultimate_0278"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 278}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
