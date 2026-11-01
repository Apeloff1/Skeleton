"""Emote ultimate 0260.
"""
from __future__ import annotations

ID = "emote_ultimate_0260"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 260}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
