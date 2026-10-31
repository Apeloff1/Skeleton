"""Emote apex 0103.
"""
from __future__ import annotations

ID = "emote_apex_0103"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
