"""Emote ultimate 0210.
"""
from __future__ import annotations

ID = "emote_ultimate_0210"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 210}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
