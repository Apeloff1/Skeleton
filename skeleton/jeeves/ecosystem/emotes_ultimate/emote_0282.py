"""Emote ultimate 0282.
"""
from __future__ import annotations

ID = "emote_ultimate_0282"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 282}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
