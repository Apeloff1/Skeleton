"""Emote ultimate 0163.
"""
from __future__ import annotations

ID = "emote_ultimate_0163"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 163}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
