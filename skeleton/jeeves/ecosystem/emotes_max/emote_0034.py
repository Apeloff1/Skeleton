"""Emote max 0034.
"""
from __future__ import annotations

ID = "emote_max_0034"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 34}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
