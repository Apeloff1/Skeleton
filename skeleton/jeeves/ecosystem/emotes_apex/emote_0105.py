"""Emote apex 0105.
"""
from __future__ import annotations

ID = "emote_apex_0105"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 105}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
