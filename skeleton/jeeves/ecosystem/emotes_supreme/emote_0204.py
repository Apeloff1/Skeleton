"""Emote supreme 0204.
"""
from __future__ import annotations

ID = "emote_supreme_0204"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 204}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
