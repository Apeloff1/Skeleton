"""Emote apex 0093.
"""
from __future__ import annotations

ID = "emote_apex_0093"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 93}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
