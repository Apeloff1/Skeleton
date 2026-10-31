"""Emote apex 0084.
"""
from __future__ import annotations

ID = "emote_apex_0084"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 84}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
