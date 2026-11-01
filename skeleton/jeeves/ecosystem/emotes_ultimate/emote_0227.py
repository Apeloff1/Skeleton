"""Emote ultimate 0227.
"""
from __future__ import annotations

ID = "emote_ultimate_0227"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 227}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
