"""Emote ultimate 0138.
"""
from __future__ import annotations

ID = "emote_ultimate_0138"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 138}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
