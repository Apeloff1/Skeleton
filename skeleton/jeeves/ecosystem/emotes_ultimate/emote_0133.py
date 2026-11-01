"""Emote ultimate 0133.
"""
from __future__ import annotations

ID = "emote_ultimate_0133"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
