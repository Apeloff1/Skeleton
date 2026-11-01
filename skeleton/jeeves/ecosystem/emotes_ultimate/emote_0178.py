"""Emote ultimate 0178.
"""
from __future__ import annotations

ID = "emote_ultimate_0178"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 178}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
