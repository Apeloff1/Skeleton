"""Emote ultimate 0218.
"""
from __future__ import annotations

ID = "emote_ultimate_0218"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "index": 218}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
