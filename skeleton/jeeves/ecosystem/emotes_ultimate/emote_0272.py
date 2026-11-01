"""Emote ultimate 0272.
"""
from __future__ import annotations

ID = "emote_ultimate_0272"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 272}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
