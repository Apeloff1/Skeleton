"""Emote ultimate 0284.
"""
from __future__ import annotations

ID = "emote_ultimate_0284"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 284}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
