"""Emote mega 0006.
"""
from __future__ import annotations

ID = "emote_mega_0006"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 6}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
