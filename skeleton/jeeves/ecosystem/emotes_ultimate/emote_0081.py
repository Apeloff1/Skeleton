"""Emote ultimate 0081.
"""
from __future__ import annotations

ID = "emote_ultimate_0081"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 81}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
