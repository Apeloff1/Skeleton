"""Emote ultimate 0201.
"""
from __future__ import annotations

ID = "emote_ultimate_0201"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 201}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
