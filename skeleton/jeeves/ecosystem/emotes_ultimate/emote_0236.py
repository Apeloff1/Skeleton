"""Emote ultimate 0236.
"""
from __future__ import annotations

ID = "emote_ultimate_0236"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 236}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
