"""Emote ultimate 0225.
"""
from __future__ import annotations

ID = "emote_ultimate_0225"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 225}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
