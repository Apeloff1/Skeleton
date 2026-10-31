"""Emote max 0087.
"""
from __future__ import annotations

ID = "emote_max_0087"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 87}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
