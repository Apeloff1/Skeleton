"""Emote ultimate 0186.
"""
from __future__ import annotations

ID = "emote_ultimate_0186"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 186}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
