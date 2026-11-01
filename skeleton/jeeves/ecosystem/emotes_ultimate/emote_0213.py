"""Emote ultimate 0213.
"""
from __future__ import annotations

ID = "emote_ultimate_0213"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 213}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
