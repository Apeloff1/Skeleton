"""Emote apex 0027.
"""
from __future__ import annotations

ID = "emote_apex_0027"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
