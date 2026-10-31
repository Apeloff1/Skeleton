"""Emote max 0012.
"""
from __future__ import annotations

ID = "emote_max_0012"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 12}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
