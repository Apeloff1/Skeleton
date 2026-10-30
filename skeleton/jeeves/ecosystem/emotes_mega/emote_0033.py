"""Emote mega 0033.
"""
from __future__ import annotations

ID = "emote_mega_0033"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 33}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
