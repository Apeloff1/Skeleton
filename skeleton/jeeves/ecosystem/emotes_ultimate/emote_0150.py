"""Emote ultimate 0150.
"""
from __future__ import annotations

ID = "emote_ultimate_0150"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 150}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
