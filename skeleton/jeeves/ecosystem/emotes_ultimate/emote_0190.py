"""Emote ultimate 0190.
"""
from __future__ import annotations

ID = "emote_ultimate_0190"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 190}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
